"""LoRA / QLoRA fine-tuning of the SLM adjudicator on labelled rows (`viveka train-slm`).

Loss is on the completion only (label + end-of-turn), never on the prompt, and the
prompt/completion tokens come from `viveka.models.slm.ChatFormat`, the exact tokenisation
the scorer uses. After training, the adapter is scored on the dev file with the same
label-likelihood scorer used in production, and `viveka_adapter.json` records what it was
trained on.

Needs the `llm` and `train` extras and a CUDA GPU for sensible speed (QLoRA on 6 GB fits
Qwen3-1.7B with the defaults).
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from viveka.labels import LABELS
from viveka.models.slm import (
    PROMPT_VERSION,
    ChatFormat,
    LabelScorer,
    resolve_device,
    resolve_dtype,
)
from viveka.train.sft import read_jsonl

log = logging.getLogger(__name__)

LORA_TARGETS = ("q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj")


@dataclass
class TrainConfig:
    train: str
    out: str
    dev: str | None = None
    model: str = "Qwen/Qwen3-1.7B"
    epochs: float = 2.0
    lr: float = 2e-4
    batch_size: int = 4
    grad_accum: int = 4
    max_len: int = 1536
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    qlora: bool = True
    seed: int = 7
    limit: int | None = None
    eval_limit: int | None = 300


class _Examples:
    """Tokenised (input_ids, labels) pairs with the prompt masked out of the loss."""

    def __init__(self, records: list[dict], fmt: ChatFormat, max_len: int):
        self.items: list[dict[str, list[int]]] = []
        self.skipped = 0
        for r in records:
            prompt = fmt.prompt_ids(r["messages"])
            answer = fmt.completion_ids(r["label"])
            if len(prompt) + len(answer) > max_len:
                self.skipped += 1
                continue
            self.items.append(
                {"input_ids": prompt + answer, "labels": [-100] * len(prompt) + answer}
            )

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> dict[str, list[int]]:
        return self.items[i]


class _Collator:
    def __init__(self, pad_id: int):
        self.pad_id = pad_id

    def __call__(self, batch: list[dict[str, list[int]]]) -> dict[str, Any]:
        import torch

        width = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), width), self.pad_id, dtype=torch.long)
        labels = torch.full((len(batch), width), -100, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            ids[i, :n] = torch.tensor(b["input_ids"])
            labels[i, :n] = torch.tensor(b["labels"])
            mask[i, :n] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}


def _load_base(cfg: TrainConfig) -> tuple[Any, Any, str, Any, bool]:
    from transformers import AutoModelForCausalLM, AutoTokenizer

    device = resolve_device("auto")
    dtype = resolve_dtype("auto", device)
    tok = AutoTokenizer.from_pretrained(cfg.model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    kwargs: dict[str, Any] = {"dtype": dtype}
    use_4bit = cfg.qlora and device == "cuda"
    if use_4bit:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = {"": 0}
    elif cfg.qlora:
        log.warning("QLoRA needs CUDA; training a plain LoRA in %s on %s", dtype, device)
    model = AutoModelForCausalLM.from_pretrained(cfg.model, **kwargs)
    if not use_4bit:
        model = model.to(device)
    model.config.use_cache = False
    return tok, model, device, dtype, use_4bit


def evaluate_records(model, tok, records: list[dict], limit: int | None = None) -> dict:
    """Accuracy and macro-F1 of the label-likelihood scorer on exported records."""
    from sklearn.metrics import accuracy_score, f1_score

    if limit:
        records = random.Random(0).sample(records, min(limit, len(records)))
    model.eval()
    model.config.use_cache = True
    scorer = LabelScorer(model, tok)
    started = time.perf_counter()
    preds = [
        LABELS[int(np.argmax(scorer.logprobs(scorer.fmt.prompt_ids(r["messages"]))))]
        for r in records
    ]
    elapsed = time.perf_counter() - started
    gold = [r["label"] for r in records]
    return {
        "rows": len(records),
        "accuracy": accuracy_score(gold, preds),
        "macro_f1": f1_score(gold, preds, average="macro", zero_division=0),
        "seconds_per_row": elapsed / max(len(records), 1),
    }


def train(cfg: TrainConfig) -> dict[str, Any]:
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import Trainer, TrainingArguments, set_seed

    set_seed(cfg.seed)
    out = Path(cfg.out)
    tok, model, device, dtype, use_4bit = _load_base(cfg)
    fmt = ChatFormat(tok)

    records = read_jsonl(cfg.train)
    if cfg.limit:
        records = random.Random(cfg.seed).sample(records, min(cfg.limit, len(records)))
    stale = {r.get("prompt_version") for r in records} - {PROMPT_VERSION, None}
    if stale:
        raise ValueError(f"{cfg.train} was exported with prompt {stale}; re-run export-sft")
    train_set = _Examples(records, fmt, cfg.max_len)
    dev_records = read_jsonl(cfg.dev) if cfg.dev else []
    eval_set = _Examples(dev_records[:200], fmt, cfg.max_len) if dev_records else None
    log.info("train %d rows (%d over max_len skipped)", len(train_set), train_set.skipped)

    if use_4bit:
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        model.enable_input_require_grads()
    model = get_peft_model(
        model,
        LoraConfig(
            r=cfg.lora_r,
            lora_alpha=cfg.lora_alpha,
            lora_dropout=cfg.lora_dropout,
            target_modules=list(LORA_TARGETS),
            bias="none",
            task_type="CAUSAL_LM",
        ),
    )
    model.print_trainable_parameters()

    args = TrainingArguments(
        output_dir=str(out / "checkpoints"),
        num_train_epochs=cfg.epochs,
        per_device_train_batch_size=cfg.batch_size,
        per_device_eval_batch_size=cfg.batch_size,
        gradient_accumulation_steps=cfg.grad_accum,
        learning_rate=cfg.lr,
        lr_scheduler_type="cosine",
        warmup_steps=10,
        logging_steps=10,
        eval_strategy="epoch" if eval_set else "no",
        save_strategy="no",
        bf16=dtype == torch.bfloat16,
        fp16=dtype == torch.float16,
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        report_to=[],
        remove_unused_columns=False,
        seed=cfg.seed,
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_set,
        eval_dataset=eval_set,
        data_collator=_Collator(tok.pad_token_id),
    )
    started = time.perf_counter()
    result = trainer.train()
    train_seconds = time.perf_counter() - started

    out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out)
    tok.save_pretrained(out)
    dev_metrics = evaluate_records(model, tok, dev_records, cfg.eval_limit) if dev_records else None
    meta = {
        "base_model": cfg.model,
        "prompt_version": PROMPT_VERSION,
        "labels": list(LABELS),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "train_rows": len(train_set),
        "train_loss": result.training_loss,
        "train_seconds": round(train_seconds, 1),
        "device": device,
        "qlora": use_4bit,
        "config": asdict(cfg),
        "dev": dev_metrics,
    }
    (out / "viveka_adapter.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta

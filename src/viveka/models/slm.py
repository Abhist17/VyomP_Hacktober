"""SLM adjudicator: an open-weight causal LM (Qwen3-1.7B by default, + LoRA) scoring labels.

The model never free-generates. For each row it reads the prompt once, then scores the
log-probability of every one of the 27 exact label strings (each followed by the chat
end-of-turn marker, so "Purchase" cannot win by being a prefix of "Purchase Order").
A softmax over the 27 sequence scores is the opinion handed to fusion, so the output is
always a valid label with a full probability distribution.

The same prompt builder and tokenisation are used by `viveka.train.slm`, so a LoRA adapter
trained there scores exactly the text it was trained on. Zero-shot is the same scorer with
no adapter.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import logging
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from viveka.context import Context
from viveka.labels import LABELS
from viveka.normalise import is_blank
from viveka.signals import EvidenceCard

log = logging.getLogger(__name__)

# Bump when the prompt text changes; adapters record the version they were trained on.
PROMPT_VERSION = "v1"

SYSTEM_PROMPT = """You are an Indian chartered accountant booking transactions in TallyPrime
for one company.
Pick exactly one voucher type for the transaction, from the company's own books.
Decide from structure, not keywords: whose books these are, which legs are the company's own
cash or bank accounts, whether goods, money or only documents moved, and whether the supply
crossed India's border. Answer with the voucher type only."""

LABEL_BLOCK = "Voucher types:\n" + "\n".join(f"- {label}" for label in LABELS)


def row_text(row: Mapping[str, object]) -> str:
    """Compact `field: value` serialisation of the non-empty canonical and extra fields."""
    parts = [
        f"{str(k).removeprefix('extra:')}: {v}"
        for k, v in row.items()
        if not str(k).startswith("_") and not is_blank(v)
    ]
    return "\n".join(parts)


def books_line(ctx: Context | None) -> str:
    if ctx is None or not (ctx.company_name or ctx.company_gstin):
        return "Books of: unknown company"
    who = ctx.company_name or "?"
    gst = f", GSTIN {ctx.company_gstin}" if ctx.company_gstin else ""
    own = sorted(ctx.own_accounts)
    accounts = f"\nOwn cash/bank ledgers: {', '.join(own)}" if own else ""
    return f"Books of: {who}{gst} ({ctx.source}){accounts}"


def build_messages(
    card: EvidenceCard,
    row: Mapping[str, object],
    ctx: Context | None,
    precedents: str = "",
) -> list[dict[str, str]]:
    """Static system turn (cacheable across rows) + one user turn for this row."""
    sections = [
        books_line(ctx),
        f"Similar verified rows:\n{precedents}" if precedents else "",
        card.render(),
        f"Transaction:\n{row_text(row)}",
        "Voucher type?",
    ]
    return [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\n\n{LABEL_BLOCK}"},
        {"role": "user", "content": "\n\n".join(s for s in sections if s)},
    ]


def build_prompt(card: EvidenceCard, row: Mapping[str, object], precedents: str = "") -> str:
    """Plain-text prompt (no chat template), kept for inspection and tests."""
    return "\n\n".join(m["content"] for m in build_messages(card, row, None, precedents))


def label_gbnf() -> str:
    """GBNF grammar that only admits the 27 label strings (llama.cpp)."""
    alts = " | ".join(json.dumps(label) for label in LABELS)
    return f"root ::= {alts}\n"


def label_json_schema() -> dict[str, Any]:
    """JSON schema for structured outputs (vLLM / llama.cpp server)."""
    return {
        "type": "object",
        "properties": {"voucher_type": {"type": "string", "enum": list(LABELS)}},
        "required": ["voucher_type"],
    }


# --- chat formatting shared with training --------------------------------------------------

_PROBE = "VIVEKA_PROBE_7f3a"


class ChatFormat:
    """Prompt / completion token ids for one tokenizer, identical in training and scoring.

    The completion is the label plus whatever the chat template puts after an assistant
    message (e.g. `<|im_end|>` for Qwen), discovered by rendering a probe answer.
    """

    def __init__(self, tokenizer: Any):
        self.tok = tokenizer
        self.has_template = bool(getattr(tokenizer, "chat_template", None))
        self.answer_prefix = ""
        self.end_text = tokenizer.eos_token or ""
        if self.has_template:
            msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
            prompt = self._render(msgs, generation=True)
            full = self._render([*msgs, {"role": "assistant", "content": _PROBE}], False)
            if full.startswith(prompt) and _PROBE in full[len(prompt) :]:
                before, after = full[len(prompt) :].split(_PROBE, 1)
                self.answer_prefix = before
                self.end_text = after.rstrip("\n") or self.end_text

    def _render(self, messages: list[dict[str, str]], generation: bool) -> str:
        return self.tok.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=generation,
            enable_thinking=False,  # Qwen3: no reasoning block; ignored by other templates
        )

    def prompt_text(self, messages: list[dict[str, str]]) -> str:
        if self.has_template:
            return self._render(messages, generation=True)
        return "\n\n".join(m["content"] for m in messages) + "\n\nAnswer: "

    def prompt_ids(self, messages: list[dict[str, str]]) -> list[int]:
        return self.tok(self.prompt_text(messages), add_special_tokens=False)["input_ids"]

    def completion_ids(self, label: str) -> list[int]:
        text = f"{self.answer_prefix}{label}{self.end_text}"
        return self.tok(text, add_special_tokens=False)["input_ids"]


class LabelScorer:
    """Log-likelihood of each label continuation after one shared prompt."""

    def __init__(self, model: Any, tokenizer: Any, label_batch: int = 9, calibrate: bool = False):
        self.model = model
        self.calibrate = calibrate
        self._prior: np.ndarray | None = None
        self.fmt = ChatFormat(tokenizer)
        self.pad_id = tokenizer.pad_token_id
        if self.pad_id is None:
            self.pad_id = tokenizer.eos_token_id or 0
        self.label_ids = [self.fmt.completion_ids(label) for label in LABELS]
        self.label_batch = max(1, label_batch)
        self._use_cache = True

    def logprobs(self, prompt_ids: list[int]) -> np.ndarray:
        """Sum of token log-probs of each of the 27 label continuations."""
        import torch

        device = self.model.device
        with torch.inference_mode():
            prompt = torch.tensor([prompt_ids], device=device)
            out = self.model(input_ids=prompt, use_cache=self._use_cache)
            first = torch.log_softmax(out.logits[0, -1].float(), dim=-1)
            past = out.past_key_values if self._use_cache else None
            scores = np.empty(len(LABELS))
            for start in range(0, len(LABELS), self.label_batch):
                chunk = list(range(start, min(start + self.label_batch, len(LABELS))))
                scores[chunk] = self._chunk(prompt, first, past, chunk)
        return scores

    def _chunk(self, prompt, first, past, chunk: list[int]) -> np.ndarray:
        import torch

        conts = [self.label_ids[i] for i in chunk]
        base = np.array([float(first[c[0]]) for c in conts])
        tails = [c[:-1] for c in conts]  # inputs that predict tokens 1..n-1
        width = max(len(t) for t in tails)
        if width == 0:
            return base
        k, device = len(chunk), self.model.device
        inp = torch.full((k, width), self.pad_id, dtype=torch.long, device=device)
        for j, t in enumerate(tails):
            if t:
                inp[j, : len(t)] = torch.tensor(t, device=device)

        logits = None
        if past is not None and self._use_cache:
            try:
                cache = copy.deepcopy(past)
                cache.batch_repeat_interleave(k)
                # Right padding: pad tokens sit after every real token, so they never
                # influence the positions that are read, and an all-ones mask is exact.
                mask = torch.ones((k, prompt.shape[1] + width), dtype=torch.long, device=device)
                logits = self.model(
                    input_ids=inp, past_key_values=cache, attention_mask=mask, use_cache=True
                ).logits
            except (AttributeError, TypeError, RuntimeError) as exc:
                log.warning("KV-cache reuse unavailable (%s); scoring without cache", exc)
                self._use_cache = False
        if logits is None:
            full = torch.cat([prompt.expand(k, -1), inp], dim=1)
            logits = self.model(input_ids=full, use_cache=False).logits[:, prompt.shape[1] :]

        lp = torch.log_softmax(logits.float(), dim=-1)
        out = base.copy()
        for j, c in enumerate(conts):
            for t in range(1, len(c)):
                out[j] += float(lp[j, t - 1, c[t]])
        return out

    def prior(self) -> np.ndarray:
        """Label scores for a content-free row (contextual calibration, Zhao et al. 2021).

        Subtracting them removes a zero-shot model's bias toward short or frequent label
        strings; a fine-tuned adapter does not need it.
        """
        if self._prior is None:
            empty = build_messages(EvidenceCard(row_id=0), {"narration": "N/A"}, None)
            self._prior = self.logprobs(self.fmt.prompt_ids(empty))
        return self._prior

    def distribution(self, prompt_ids: list[int], temperature: float = 1.0) -> np.ndarray:
        s = self.logprobs(prompt_ids)
        if self.calibrate:
            s = s - self.prior()
        s = s / max(temperature, 1e-6)
        s -= s.max()
        p = np.exp(s)
        return p / p.sum()


# --- model loading -------------------------------------------------------------------------

_LOADED: dict[tuple, tuple[Any, Any]] = {}


def resolve_device(device: str = "auto") -> str:
    import torch

    if device != "auto":
        return device
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_dtype(dtype: str, device: str):
    import torch

    if dtype != "auto":
        return getattr(torch, dtype)
    if device == "cuda":
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return torch.float16 if device == "mps" else torch.float32


def load_model(
    model: str,
    adapter: str = "",
    device: str = "auto",
    dtype: str = "auto",
    load_in_4bit: bool = False,
) -> tuple[Any, Any]:
    """Load (and memoise) tokenizer + model, with the LoRA adapter applied when given."""
    key = (model, adapter, device, dtype, load_in_4bit)
    if key in _LOADED:
        return _LOADED[key]
    from transformers import AutoModelForCausalLM, AutoTokenizer

    dev = resolve_device(device)
    torch_dtype = resolve_dtype(dtype, dev)
    kwargs: dict[str, Any] = {"dtype": torch_dtype}
    if load_in_4bit and dev == "cuda":
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch_dtype,
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = {"": 0}
    has_tok = adapter and (Path(adapter) / "tokenizer_config.json").is_file()
    tokenizer = AutoTokenizer.from_pretrained(adapter if has_tok else model)
    lm = AutoModelForCausalLM.from_pretrained(model, **kwargs)
    if adapter:
        from peft import PeftModel

        _check_adapter(Path(adapter), model)
        lm = PeftModel.from_pretrained(lm, adapter)
    if "device_map" not in kwargs:
        lm = lm.to(dev)
    lm.eval()
    _LOADED[key] = (tokenizer, lm)
    return tokenizer, lm


def _check_adapter(path: Path, model: str) -> None:
    meta = path / "viveka_adapter.json"
    if not meta.is_file():
        return
    info = json.loads(meta.read_text(encoding="utf-8"))
    if info.get("labels") and list(info["labels"]) != list(LABELS):
        raise ValueError(f"Adapter {path} was trained on a different label list")
    if info.get("prompt_version") != PROMPT_VERSION:
        log.warning(
            "Adapter trained on prompt %s, scoring with %s",
            info.get("prompt_version"),
            PROMPT_VERSION,
        )
    if info.get("base_model") and info["base_model"] != model:
        log.warning("Adapter base model %s differs from %s", info["base_model"], model)


def model_is_local(model: str) -> bool:
    """True when the weights are on disk (a directory or the Hugging Face cache)."""
    if Path(model).is_dir():
        return True
    try:
        from huggingface_hub import try_to_load_from_cache
    except ImportError:
        return False
    return isinstance(try_to_load_from_cache(model, "config.json"), str)


class SLMAdjudicator:
    name = "slm"

    def __init__(self, config: Mapping[str, Any]):
        self.backend = config.get("backend", "transformers")
        self.model = config.get("model", "Qwen/Qwen3-1.7B")
        self.adapter = str(config.get("adapter", "") or "")
        self.device = config.get("device", "auto")
        self.dtype = config.get("dtype", "auto")
        self.load_in_4bit = bool(config.get("load_in_4bit", False))
        self.label_batch = int(config.get("label_batch", 9))
        self.temperature = float(config.get("temperature", 1.0))
        self.enabled = bool(config.get("enabled", True))
        self.allow_download = bool(config.get("allow_download", False))
        self.zero_shot_calibration = bool(config.get("zero_shot_calibration", False))
        self._scorer: LabelScorer | None = None

    @property
    def adapter_path(self) -> str:
        """The configured adapter if it exists on disk, else "" (zero-shot)."""
        return self.adapter if self.adapter and Path(self.adapter).is_dir() else ""

    @property
    def version(self) -> str:
        tail = Path(self.adapter_path).name if self.adapter_path else "zero-shot"
        return f"{self.model}+{tail}"

    def available(self) -> bool:
        if not self.enabled or os.environ.get("VIVEKA_SLM", "").lower() in {"0", "off", "false"}:
            return False
        if self.backend != "transformers":
            return False
        if importlib.util.find_spec("torch") is None:
            return False
        if importlib.util.find_spec("transformers") is None:
            return False
        if self.adapter_path and importlib.util.find_spec("peft") is None:
            return False
        return self.allow_download or model_is_local(self.model)

    def scorer(self) -> LabelScorer:
        if self._scorer is None:
            tok, lm = load_model(
                self.model, self.adapter_path, self.device, self.dtype, self.load_in_4bit
            )
            calibrate = self.zero_shot_calibration and not self.adapter_path
            self._scorer = LabelScorer(lm, tok, self.label_batch, calibrate)
        return self._scorer

    def score(
        self,
        cards: Sequence[EvidenceCard],
        rows: Sequence[Mapping[str, object]],
        ctx: Context | None = None,
    ) -> np.ndarray:
        if not cards:
            return np.zeros((0, len(LABELS)))
        scorer = self.scorer()
        return np.vstack(
            [
                scorer.distribution(
                    scorer.fmt.prompt_ids(build_messages(card, row, ctx)), self.temperature
                )
                for card, row in zip(cards, rows, strict=True)
            ]
        )

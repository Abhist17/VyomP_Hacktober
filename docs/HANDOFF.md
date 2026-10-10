# Handoff: train the Viveka SLM

This note is for the teammate (and their Claude Code session) who will train the model.
Read it top to bottom before running anything.

## What Viveka is

Viveka is our entry for Hacktober PS4, "VYOM+ Intelligent Voucher Classification". It reads an
Excel file of structured transactions and assigns each row one of 27 voucher types, such as
Purchase, Sales, Contra or Rejection In. PS4 requires an open-source LLM or SLM as the
**primary intelligence layer**, so the fine-tuned SLM is the most important part of the
submission. Judging looks at:

- accuracy, macro-F1 and per-class scores
- confusable pairs (Purchase vs Sales, Contra vs Payment, and so on)
- ambiguous and missing fields
- consistent output
- speed and compute cost

The real dataset is not available yet, so we train and evaluate on synthetic books.

## Architecture

| Opinion source | File | Role |
|---|---|---|
| Rules | `src/viveka/models/rules.py` | Labelling functions over the evidence card. Always available. |
| Sentinel | `src/viveka/models/sentinel.py` | Classifier over row text (TF-IDF or an embedding model) plus signals, using logistic regression. Trains in about 15 s on CPU. |
| SLM | `src/viveka/models/slm.py` | Qwen3-1.7B, plus a LoRA adapter after training. The main engine. |

The opinions are fused in `src/viveka/fusion.py`, with weights set in `policies/default.toml`
(the SLM's weight is 2). Then the guardrails run.

How the SLM produces an opinion:

- It never free-generates text.
- For each row it reads the prompt once and scores the log-likelihood of all 27 label
  strings, each followed by the chat end-of-turn token. The 27 continuations share the
  prompt's KV cache.
- A softmax over those scores gives a full probability distribution, so every answer is a
  valid label and comes with a confidence.

Training and scoring use the same prompt builder (`build_messages`) and the same
tokenisation (`ChatFormat`), so an adapter scores exactly the text it was trained on.

`fast` mode sends a row to the SLM only when the cheap sources are unsure or disagree
(`gather_opinions` in `pipeline.py`).

## Status when this was handed over

**Verified** (on the original laptop, CPU only):

- `viveka synth` builds the three splits (3000 / 600 / 800 rows) in under a second. Every
  column header maps to a canonical field, whose books is inferred correctly for every file,
  and the rows join to the gold files.
- `viveka export-sft` and `viveka train-sentinel` both work.
- `viveka bench` runs.
- On the unseen test split:

  | Config | Accuracy | Macro-F1 | Seen templates | Held-out templates |
  |---|---|---|---|---|
  | rules | 77.2% | 76.3% | 84.1% | 70.4% |
  | sentinel | 84.6% | 84.1% | 98.8% | 70.4% |
  | rules+sentinel | 81.9% | 81.7% | 94.5% | 69.1% |

  The held-out templates are where the SLM has to win. They are event shapes that never
  appear in training.
- `LabelScorer` was checked with Qwen3-0.6B on CPU. The cached and uncached paths agree to
  within 3e-5, and the cache is about 15× faster. The end marker detected for Qwen3 is
  `<|im_end|>` with an empty answer prefix.
- `ruff check` and `ruff format` are clean. The 22 existing tests pass.

**Not verified yet:**

- `viveka train-slm` has never completed a run. The first smoke run stopped on
  `warmup_ratio`, an argument that transformers 5.x no longer accepts. It was changed to
  `warmup_steps=10` and has not been run since.
- QLoRA (bitsandbytes) has never been tried. No GPU was available.
- Zero-shot Qwen3-1.7B has not been benchmarked. Zero-shot Qwen3-0.6B was very weak (about
  1 in 12 right), which is expected.
- There are no new tests yet for `synth`, `sentinel`, `bench` or `train`.

## Setup on the training laptop

Use Python 3.12 and a CUDA GPU. 6 GB is enough for QLoRA on Qwen3-1.7B.

```bash
git clone <repo> && cd VyomP_Hacktober
git checkout feat/viveka-scaffold-and-workbench
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
# Linux: PyPI torch already includes CUDA.
# Windows: install the CUDA wheel first:
#   pip install torch --index-url https://download.pytorch.org/whl/cu124
pip install -e ".[llm,train,api]" pytest hypothesis ruff
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
viveka pull-model                      # Qwen/Qwen3-1.7B into the Hugging Face cache (~3.4 GB)
```

## Steps

```bash
# 1. Data. Deterministic for a given seed, so it is identical on every machine.
viveka synth --out data/synth
viveka export-sft data/synth/train --out data/sft/train.jsonl
viveka export-sft data/synth/dev   --out data/sft/dev.jsonl

# 2. Smoke run first (about 2 minutes). It checks the whole loop, not accuracy.
viveka train-slm --train data/sft/train.jsonl --dev data/sft/dev.jsonl \
  --out models/adapters/smoke --limit 64 --epochs 1

# 3. Full run. QLoRA by default when CUDA is present.
viveka train-slm --train data/sft/train.jsonl --dev data/sft/dev.jsonl \
  --out models/adapters/viveka-qwen3-1.7b
#   Prints dev accuracy and macro-F1 at the end; writes viveka_adapter.json next to the adapter.

# 4. Sentinel and benchmark on the unseen test split
viveka train-sentinel data/synth/train
viveka bench data/synth/test --out reports/bench
cat reports/bench/bench.md
```

If you run out of GPU memory, try these in order:

1. `--batch-size 2 --grad-accum 8`
2. `--max-len 1024` (check the "over max_len skipped" count in the log)
3. `--model Qwen/Qwen3-0.6B`

Prompts are about 700 tokens.

## Tasks for Claude on the training laptop, in order

1. **Get `train-slm` working end to end** with the smoke command. This is likely where
   things break.
   - transformers is 5.x, so expect changes in `TrainingArguments` or `Trainer` argument
     names. Check the current docs; don't guess.
   - Also check that `prepare_model_for_kbit_training` and gradient checkpointing work
     together. If the loss is `nan` or zero, check the label masking in
     `train/slm.py:_Examples`. It should give `-100` on prompt tokens and real ids on the
     completion.
2. **Run the full training.** Then check that `viveka bench` shows `slm-fine-tuned` above
   `sentinel`, especially on held-out templates.
   - **If the fine-tuned SLM doesn't beat zero-shot plus retrieval or the sentinel**, don't
     hide it. The README's decision rule says the harness decides what ships.
3. **Tune the fusion.**
   - Set `[opinions]` weights in `policies/default.toml` using the **dev** split, never the
     test split.
   - If the fine-tuned SLM clearly wins, raise `slm` to 3–4 or leave `rules` out.
   - Then set `[decision] fast_threshold` so `fused-fast` stays within about 1 point of
     `fused` while sending far fewer rows to the SLM.
4. **Check zero-shot calibration.** Bench `slm-zero-shot` with
   `zero_shot_calibration = true` and with `false` under `[slm]`, and keep whichever scores
   higher.
5. **Write tests** for:
   - `synth`: determinism for a seed, all 27 labels in every split, test companies
     disjoint from train, every header aligned.
   - `sentinel`: fit, save, load and score shapes on a small split.
   - `ChatFormat` and `LabelScorer`: use a tiny model and assert that the cached and
     uncached scores match.

   Set `VIVEKA_SLM=off` in the existing tests, or they will load the model when the weights
   are cached.
6. **Send back:**
   - the folder `models/adapters/viveka-qwen3-1.7b/` (adapter safetensors, tokenizer files,
     `viveka_adapter.json`; tens of MB)
   - `reports/bench/bench.md` and `bench.json`

   `.gitignore` excludes `models/adapters/` and `*.safetensors`, so share the adapter as a
   zip or a Hugging Face repo, not through git.

## Gotchas

- `[slm] allow_download = false`: the SLM only counts as available when its weights are
  already local. Run `viveka pull-model` first. If you skip it, the SLM is silently skipped
  and `bench` reports "skipped".
- `PROMPT_VERSION` in `models/slm.py`: any change to the prompt text needs a version bump, a
  fresh `export-sft` and retraining. `train-slm` refuses JSONL exported with a different
  version.
- The adapter folder must sit at the path in `[slm] adapter`, or be passed through a policy
  copy. If it isn't found, the pipeline falls back to zero-shot.
- `[slm] revision` is not wired into `from_pretrained` yet.
- The sentinel bundle is a joblib pickle. Load only bundles you trained yourself.
- Synthetic data has known limits: one company's books per file, and about 2–4 templates per
  class. When the real Excel file arrives, extend the `schema.py` synonyms, label part of it
  as a gold dev set, and retrain on synthetic plus real data.

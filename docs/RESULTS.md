# Results: training the Viveka SLM

Status as of 2026-10-10. This note follows on from [HANDOFF.md](HANDOFF.md) and records what was
run on the training laptop. Numbers marked _pending_ are filled in when the full run finishes.

## Hardware and software

| | |
|---|---|
| GPU | NVIDIA GeForce RTX 4050 Laptop, 6 GB (Windows 11, WDDM) |
| Python | 3.12.4 |
| torch | 2.6.0+cu124 |
| transformers | 5.19.0 |
| peft | 0.21.2 |
| bitsandbytes | 0.50.2 |

## What is now verified

- **`viveka train-slm` runs end to end with QLoRA on CUDA.** No code changes were needed on
  transformers 5.19; the `warmup_steps=10` fix from the handoff holds. The smoke run (64 rows,
  1 epoch) trained, ran the per-epoch eval and saved the adapter.
- **QLoRA with gradient checkpointing works.** The loss is finite and falls steadily (below), so
  the label masking in `train/slm.py:_Examples` is correct.
- **No prompt exceeds `max_len` 1536.** `train 3000 rows (0 over max_len skipped)`.
- **Data is reproducible.** `viveka synth` with seed 7 regenerated the same 3000 / 600 / 800
  rows, and the CPU baselines below match the handoff to the decimal.

## Full training run

```bash
viveka train-slm --train data/sft/train.jsonl --dev data/sft/dev.jsonl \
  --out models/adapters/viveka-qwen3-1.7b --batch-size 2 --grad-accum 8
```

Qwen/Qwen3-1.7B, 4-bit NF4 QLoRA, LoRA r=16 / alpha=32 on all attention and MLP projections,
2 epochs, lr 2e-4 cosine, effective batch 16, 376 steps.

- **Speed:** about 25-29 s per step, about 2 h 40 min in total. VRAM sits at about 5.8 of 6 GB,
  most of it the 151k-token vocabulary's logits. `--batch-size 2 --grad-accum 8` was no faster
  than the default 4 x 4, so the batch is not the bottleneck.
- **Loss** is on the completion only (label plus end-of-turn):

  | Epoch | 0.05 | 0.16 | 0.27 | 0.48 | 0.75 | 0.96 | 1.0 (dev) | 2.0 (dev) |
  |---|---|---|---|---|---|---|---|---|
  | Loss | 2.99 | 0.41 | 0.19 | 0.12 | 0.056 | 0.018 | **0.0137** | _pending_ |

- **Dev accuracy and macro-F1** from the production label scorer: _pending_ (written to
  `viveka_adapter.json`).

## Benchmark on the unseen test split

800 rows, 4 companies that never appear in train, half of them in a column dialect that never
appears in train. "Held-out templates" are event shapes that never appear in training.

| Config | Accuracy | Macro-F1 | Seen templates | Held-out templates | Rows/s |
|---|---|---|---|---|---|
| rules | 77.2% | 76.3% | 84.1% | 70.4% | 3283 |
| sentinel | 84.6% | 84.1% | 98.8% | 70.4% | 1132 |
| rules+sentinel | 81.9% | 81.7% | 94.5% | 69.1% | 1645 |
| slm-fine-tuned | _pending_ | | | | |
| fused | _pending_ | | | | |
| fused-fast | _pending_ | | | | |

The hardest pairs for the CPU sources are **Purchase Return vs Sales Return** (36-41% error) and
**inventory movement vs Purchase / Sales** (17-34% error).

## Findings

- **The sentinel is not perspective-aware.** A credit note reads the same whichever company's
  books it sits in, so the sentinel does not flip Purchase Return to Sales Return when the
  books change. The rules do, and the SLM's prompt includes whose books it is. This is one
  reason the Purchase Return vs Sales Return error rate is high, and fusion should rely on
  the rules and the SLM for direction.
- **Tests now ignore local model files.** `tests/conftest.py` points the policy at a missing
  sentinel and turns the SLM off. Before, `test_perspective_swap_flips_directional_labels`
  failed on any machine that had run `viveka train-sentinel`.

## Tests added

`tests/test_synth.py` covers:

- the same seed gives identical gold files
- all 27 labels appear in every split
- test companies are disjoint from train, and only test has held-out rows
- every header aligns, except the generator's distractor columns (`Shift`, `Leave Type`,
  `Variance`)
- the sentinel fits, saves, loads and scores with the right shapes, and the loaded and fitted
  scores agree

`pytest`: 21 passed, 1 skipped (an SLM test, since the SLM is off in tests). `ruff check` and
`ruff format` are clean.

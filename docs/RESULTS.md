# Results: training the Viveka SLM

Status as of 2026-10-10, final. This note follows on from [HANDOFF.md](HANDOFF.md) and records
what was run on the training laptop: the fine-tuning run, fusion tuning, and the held-out test.

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

- **Speed:** about 25-30 s per step, 3 h 06 min in total (11,158 s). VRAM sits at about 5.8 of 6 GB,
  most of it the 151k-token vocabulary's logits. `--batch-size 2 --grad-accum 8` was no faster
  than the default 4 x 4, so the batch is not the bottleneck.
- **Loss** is on the completion only (label plus end-of-turn):

  | Epoch | 0.05 | 0.16 | 0.27 | 0.48 | 0.75 | 0.96 | 1.0 (dev) | 2.0 (dev) |
  |---|---|---|---|---|---|---|---|---|
  | Loss | 2.99 | 0.41 | 0.19 | 0.12 | 0.056 | 0.018 | **0.0137** | **0.0031** |

- **Mean train loss** 0.153 over 2 epochs.
- **Dev accuracy 98.3%, macro-F1 98.4%** on 300 SFT dev rows, from the production label scorer
  (`viveka_adapter.json`). At inference in bf16 the scorer takes about 0.5 s per row on the
  RTX 4050, KV-cache shared across the 27 label continuations.

## Benchmark on the unseen test split

800 rows, 4 companies that never appear in train, half of them in a column dialect that never
appears in train. "Held-out templates" are event shapes that never appear in training (398 of
the 800 rows). Every number below comes from `viveka tune-fusion` (`reports/tune/tune.json`),
which fits on the 600-row dev split and only then scores test.

| Config | Accuracy | Macro-F1 | Seen templates | Held-out templates | Auto-accepted | Precision of auto-accepted |
|---|---|---|---|---|---|---|
| rules | 77.3% | 76.3% | 84.1% | 70.4% | 66.0% | 82.0% |
| sentinel | 84.6% | 84.1% | 98.8% | 70.4% | 52.9% | 98.8% |
| slm (zero-shot Qwen3-1.7B, no adapter) | 19.8% | 16.7% | 21.4% | 18.1% | 46.6% | 28.2% |
| slm (fine-tuned Qwen3-1.7B) | 87.6% | 86.5% | 95.3% | 79.9% | 83.4% | 93.9% |
| fused, hand-set weights (before) | 90.5% | 89.9% | 97.0% | 83.9% | 43.5% | 96.6% |
| **fused, tuned on dev (in use)** | **91.3%** | **90.9%** | **98.8%** | 83.7% | **75.1%** | **97.2%** |

Auto-accept columns for single sources and the hand-set fusion use the earlier cut-off (0.90
confidence and a 95% prediction set). The zero-shot row is the same label scorer with no
adapter and no calibration: fine-tuning is what makes the SLM useful.

Tuned fusion is a weighted geometric mean (log pooling) of rules, sentinel and the fine-tuned
SLM with equal weights, and an auto-accept cut-off of 0.96: the lowest that keeps **dev**
precision of auto-accepted rows at 99.5%. Against the hand-set fusion it is more accurate and
sends far fewer rows to review (24.9% instead of 56.5%) while the auto-accepted rows are
*more* precise.

### End-to-end check and run modes

`viveka bench data/synth/test --only fused fused-fast` runs the real pipeline (alignment,
context, all three sources, fusion, guardrails) on the same 800 rows with the tuned policy. It
reproduces the tuned figures exactly, so the cached-opinion tuning matches production.

| Mode | Accuracy | Macro-F1 | Macro-precision | Unseen templates | Rows the SLM scored | Rows/s | Peak VRAM |
|---|---|---|---|---|---|---|---|
| `accurate` (default) | 91.2% | 90.9% | 92.7% | 83.7% | 800 | 1.33 | 4.5 GB |
| `fast` | 88.0% | 87.6% | 91.1% | 77.1% | 200 | 5.29 | 4.4 GB |

`fast` sends only the rows where rules and sentinel disagree or are unsure to the SLM: a
quarter of the rows, four times the throughput, 3.2 points of accuracy. Timings include
loading the model once, on the RTX 4050 laptop GPU.

### Fusion search on dev

`viveka tune-fusion` tries linear and log pooling with every weight in {0, 0.25, 0.5, 1} per
source (weights are scale-free, so the largest is 1) and ranks by dev accuracy, then macro-F1.

| Dev (600 rows) | Accuracy | Auto-accepted | Precision |
|---|---|---|---|
| rules | 84.3% | 67.2% | 89.1% |
| sentinel | 97.7% | 81.8% | 99.8% |
| slm (fine-tuned) | 94.8% | 95.0% | 97.0% |
| fused, hand-set | 97.0% | 57.5% | 100% |
| fused, tuned | 98.5% | 89.8% | 99.6% |

A logistic-regression stacker over the three sources' log-probabilities reached 99.0% in
5-fold cross-validation on dev against 98.7% for log pooling: two rows of 600, within noise,
so the simpler pooling rule ships.

### Choosing the auto-accept cut-off

Dev has no held-out templates, so it overstates how safe a low cut-off is. At a 99% dev target
the cut-off would be 0.76, which auto-accepts 90% of test at 95.3% precision. The stricter
99.5% target gives 0.96. On test, precision levels off near 97% even at 0.99, because the
remaining errors on unseen templates are confident ones (below).

### Remaining errors (test, tuned fusion, 70 of 800)

| Gold | Predicted | Rows |
|---|---|---|
| Advance / Prepayment | Payment | 16 |
| Material In | Rejection Out | 10 |
| Export | Sales | 6 |
| Rejection Out | Receipt Note | 6 |
| Receipt Note | Purchase | 5 |

These are the next work items. We did not tune anything against test errors.

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

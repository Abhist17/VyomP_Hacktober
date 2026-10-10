"""Command line: predict, evaluate, serve, and the data / training / benchmark commands."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from viveka.pipeline import MODES


def _predict(args: argparse.Namespace) -> int:
    from viveka.io import read_rows, write_predictions, write_table
    from viveka.pipeline import classify
    from viveka.policy import load_policy

    started = time.perf_counter()
    raw = read_rows(args.file)
    preds = classify(
        raw,
        policy=load_policy(args.policy),
        mode=args.mode,
        company_gstin=args.company_gstin,
        company_name=args.company_name,
        own_accounts=args.own_account or (),
    )
    out = Path(args.out or f"outputs/{Path(args.file).stem}.{args.format}.json")
    write_predictions(preds, out, args.format)
    if args.table:
        write_table(raw, preds, args.table)
    elapsed = time.perf_counter() - started
    review = sum(p.needs_review for p in preds)
    print(f"{len(preds)} rows -> {out} ({review} need review) in {elapsed:.2f}s", file=sys.stderr)
    return 0


def _evaluate(args: argparse.Namespace) -> int:
    from viveka.evaluate import evaluate, write_report

    report = evaluate(args.pred, args.gold)
    path = write_report(report, args.out)
    print(
        f"accuracy {report['accuracy']:.4f} · macro-F1 {report['macro_f1']:.4f} -> {path}",
        file=sys.stderr,
    )
    return 0


def _serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("Install the API extra: uv sync --extra api", file=sys.stderr)
        return 1
    uvicorn.run("viveka.api:app", host=args.host, port=args.port)
    return 0


def _synth(args: argparse.Namespace) -> int:
    from viveka.synth import generate

    m = generate(args.out, args.seed, args.train, args.dev, args.test)
    for split, files in m["splits"].items():
        rows = sum(f["rows"] for f in files)
        print(f"{split}: {len(files)} files, {rows} rows", file=sys.stderr)
    print(f"-> {args.out}/manifest.json", file=sys.stderr)
    return 0


def _export_sft(args: argparse.Namespace) -> int:
    from viveka.train.sft import export_sft

    n = export_sft(args.split_dir, args.out)
    print(f"{n} examples -> {args.out}", file=sys.stderr)
    return 0


def _train_slm(args: argparse.Namespace) -> int:
    import json
    import logging

    from viveka.train.slm import TrainConfig, train

    logging.basicConfig(level=logging.INFO)
    cfg = TrainConfig(
        train=args.train,
        dev=args.dev,
        out=args.out,
        model=args.model,
        epochs=args.epochs,
        lr=args.lr,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        max_len=args.max_len,
        lora_r=args.lora_r,
        lora_alpha=2 * args.lora_r,
        qlora=not args.no_qlora,
        seed=args.seed,
        limit=args.limit,
    )
    meta = train(cfg)
    print(json.dumps({"out": args.out, "dev": meta["dev"]}, indent=2), file=sys.stderr)
    return 0


def _train_sentinel(args: argparse.Namespace) -> int:
    from viveka.models.sentinel import Sentinel
    from viveka.train.sft import labelled_files

    cards, rows, labels = [], [], []
    for f in labelled_files(args.split_dir):
        cards += f.cards
        rows += f.rows
        labels += f.labels
    sentinel = Sentinel(args.out, args.embedder)
    started = time.perf_counter()
    sentinel.fit(cards, rows, labels)
    path = sentinel.save()
    print(f"{len(rows)} rows, {time.perf_counter() - started:.1f}s -> {path}", file=sys.stderr)
    return 0


def _bench(args: argparse.Namespace) -> int:
    from viveka.bench import bench, write_bench
    from viveka.policy import load_policy

    report = bench(args.split_dir, load_policy(args.policy), args.only, args.limit_files)
    path = write_bench(report, args.out)
    for name, r in report["results"].items():
        if "skipped" in r:
            print(f"{name:<16} skipped ({r['skipped']})", file=sys.stderr)
        else:
            print(
                f"{name:<16} acc {r['accuracy']:.4f} · macro-F1 {r['macro_f1']:.4f} · "
                f"{r['rows_per_second']} rows/s",
                file=sys.stderr,
            )
    print(f"-> {path}", file=sys.stderr)
    return 0


def _pull_model(args: argparse.Namespace) -> int:
    from huggingface_hub import snapshot_download

    from viveka.policy import load_policy

    model = args.model or load_policy(args.policy).slm.get("model", "Qwen/Qwen3-1.7B")
    path = snapshot_download(
        model,
        allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model", "*.jinja", "*.tiktoken"],
    )
    print(f"{model} -> {path}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="viveka", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("predict", help="Classify every row of an Excel / CSV / JSON file")
    p.add_argument("file")
    p.add_argument("--format", choices=("minimal", "full"), default="minimal")
    p.add_argument("--out", help="Output JSON path (default: outputs/<stem>.<format>.json)")
    p.add_argument("--table", help="Also write the sheet with prediction columns (.csv/.xlsx)")
    p.add_argument("--mode", choices=MODES, default="accurate")
    p.add_argument("--policy", help="Policy TOML (default: policies/default.toml)")
    p.add_argument("--company-gstin", help="Whose books: take the company from the profile")
    p.add_argument("--company-name")
    p.add_argument("--own-account", action="append", help="Own cash/bank ledger (repeatable)")
    p.set_defaults(func=_predict)

    e = sub.add_parser("evaluate", help="Build the evaluation report")
    e.add_argument("--pred", required=True)
    e.add_argument("--gold", required=True)
    e.add_argument("--out", default="reports/latest")
    e.set_defaults(func=_evaluate)

    s = sub.add_parser("serve", help="Start the REST API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=_serve)

    g = sub.add_parser("synth", help="Generate synthetic train / dev / test books with gold")
    g.add_argument("--out", default="data/synth")
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--train", type=int, default=3000, help="Training rows")
    g.add_argument("--dev", type=int, default=600, help="Dev rows")
    g.add_argument("--test", type=int, default=800, help="Unseen test rows")
    g.set_defaults(func=_synth)

    x = sub.add_parser("export-sft", help="Export a labelled split as SLM training JSONL")
    x.add_argument("split_dir", help="Directory of <name>.xlsx + <name>.gold.csv pairs")
    x.add_argument("--out", required=True)
    x.set_defaults(func=_export_sft)

    t = sub.add_parser("train-slm", help="LoRA / QLoRA fine-tune the SLM adjudicator")
    t.add_argument("--train", required=True, help="JSONL from export-sft")
    t.add_argument("--dev", help="JSONL from export-sft, scored after training")
    t.add_argument("--out", default="models/adapters/viveka-qwen3-1.7b")
    t.add_argument("--model", default="Qwen/Qwen3-1.7B")
    t.add_argument("--epochs", type=float, default=2.0)
    t.add_argument("--lr", type=float, default=2e-4)
    t.add_argument("--batch-size", type=int, default=4)
    t.add_argument("--grad-accum", type=int, default=4)
    t.add_argument("--max-len", type=int, default=1536)
    t.add_argument("--lora-r", type=int, default=16)
    t.add_argument("--no-qlora", action="store_true", help="bf16/fp16 LoRA instead of 4-bit")
    t.add_argument("--seed", type=int, default=7)
    t.add_argument("--limit", type=int, help="Train on a random subset (smoke runs)")
    t.set_defaults(func=_train_slm)

    n = sub.add_parser("train-sentinel", help="Fit the fast sentinel classifier")
    n.add_argument("split_dir")
    n.add_argument("--out", default="models/weights/sentinel.joblib")
    n.add_argument("--embedder", default="tfidf", help="tfidf or a sentence-transformers id")
    n.set_defaults(func=_train_sentinel)

    b = sub.add_parser("bench", help="Benchmark each opinion source and the fusion")
    b.add_argument("split_dir")
    b.add_argument("--out", default="reports/bench")
    b.add_argument("--policy")
    b.add_argument("--only", nargs="+", help="Config names to run (default: all)")
    b.add_argument("--limit-files", type=int)
    b.set_defaults(func=_bench)

    m = sub.add_parser("pull-model", help="Download the SLM weights into the HF cache")
    m.add_argument("--model", help="Default: [slm] model in the policy")
    m.add_argument("--policy")
    m.set_defaults(func=_pull_model)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

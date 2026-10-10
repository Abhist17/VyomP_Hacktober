"""Command line: `viveka predict`, `viveka evaluate`, `viveka serve`."""

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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

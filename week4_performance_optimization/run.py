#!/usr/bin/env python3
"""Run SalesLens with either the baseline or optimized engine."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from saleslens import baseline, optimized
from saleslens.data_generator import generate_dataset


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SalesLens retail transaction analytics")
    parser.add_argument("--engine", choices=("baseline", "optimized"), default="optimized")
    parser.add_argument("--data-dir", type=Path, default=Path("data/sample"))
    parser.add_argument("--generate", action="store_true", help="regenerate the dataset first")
    parser.add_argument("--rows", type=int, default=5_000, help="transaction rows when generating")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    required = [args.data_dir / name for name in ("transactions.csv", "products.csv", "customers.csv")]
    if args.generate or not all(path.exists() for path in required):
        metadata = generate_dataset(args.data_dir, args.rows, seed=args.seed)
        print(f"Generated {metadata['transaction_rows']} transaction rows in {args.data_dir}")

    engine = baseline if args.engine == "baseline" else optimized
    started = time.perf_counter()
    result = engine.analyze_directory(args.data_dir)
    elapsed = time.perf_counter() - started

    print(engine.format_report(result), end="")
    print(f"\nEngine: {args.engine} | Elapsed: {elapsed:.4f} s")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"JSON result written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

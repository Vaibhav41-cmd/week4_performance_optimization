#!/usr/bin/env python3
"""Generate cProfile and ``timeit`` evidence for SalesLens.

Outputs are written to ``results/profiles`` by default:

* ``baseline_cprofile.txt`` and ``optimized_cprofile.txt`` (tottime and
  cumulative-time views);
* ``profile_summary.json`` (call counts and parity status);
* ``microbenchmarks.json`` / ``microbenchmarks.txt`` for isolated
  data-structure operations discussed in the report.
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import timeit
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from saleslens import baseline, optimized  # noqa: E402
from saleslens.data_generator import generate_dataset  # noqa: E402


def profile_engine(name: str, function: Callable[[], dict[str, Any]], output_dir: Path, top: int) -> dict[str, Any]:
    profiler = cProfile.Profile()
    profiler.enable()
    result = function()
    profiler.disable()

    sections: list[str] = []
    stats_object: pstats.Stats | None = None
    for sort_key in ("tottime", "cumulative"):
        stream = io.StringIO()
        stats_object = pstats.Stats(profiler, stream=stream).sort_stats(sort_key)
        stats_object.print_stats(top)
        sections.append(f"\n{'=' * 88}\n{name.upper()} sorted by {sort_key}\n{'=' * 88}\n")
        sections.append(stream.getvalue())

    text_path = output_dir / f"{name}_cprofile.txt"
    text_path.write_text("\n".join(sections), encoding="utf-8")
    binary_path = output_dir / f"{name}.prof"
    profiler.dump_stats(str(binary_path))

    assert stats_object is not None
    return {
        "engine": name,
        "text_profile": str(text_path),
        "binary_profile": str(binary_path),
        "total_calls": int(stats_object.total_calls),
        "primitive_calls": int(stats_object.prim_calls),
        "profiled_seconds": float(stats_object.total_tt),
        "valid_rows": result["valid_rows"],
        "net_revenue": result["net_revenue"],
        "_result": result,
    }


def microbenchmarks() -> list[dict[str, Any]]:
    """Compare isolated implementation choices with ``timeit`` best-of-runs."""
    records = [
        {"product_id": f"P{index:05d}", "product_name": f"Product {index}"}
        for index in range(3_000)
    ]
    index = {record["product_id"]: record for record in records}
    wanted = "P02999"

    identifiers = [f"T{number:08d}" for number in range(5_000)]
    identifier_set = set(identifiers)
    keys = [f"K{number % 500:03d}" for number in range(5_000)]

    def list_bucket_total() -> float:
        buckets: list[dict[str, Any]] = []
        for key in keys:
            baseline._add_to_bucket(buckets, key, 1.0)
        return sum(bucket["revenue"] for bucket in buckets)

    def dict_bucket_total() -> float:
        buckets: defaultdict[str, float] = defaultdict(float)
        for key in keys:
            buckets[key] += 1.0
        return sum(buckets.values())

    namespace: dict[str, Any] = {
        "records": records,
        "index": index,
        "wanted": wanted,
        "find": baseline._find_by_id,
        "identifiers": identifiers,
        "identifier_set": identifier_set,
        "needle": "T00004999",
        "list_bucket_total": list_bucket_total,
        "dict_bucket_total": dict_bucket_total,
        "datetime": datetime,
    }

    specifications = [
        {
            "operation": "Master-data lookup near end of 3,000 records",
            "baseline": ("find(records, 'product_id', wanted)", 2_000),
            "optimized": ("index.get(wanted)", 50_000),
        },
        {
            "operation": "Membership test in 5,000 identifiers",
            "baseline": ("needle in identifiers", 5_000),
            "optimized": ("needle in identifier_set", 100_000),
        },
        {
            "operation": "Aggregate 5,000 values into 500 buckets",
            "baseline": ("list_bucket_total()", 5),
            "optimized": ("dict_bucket_total()", 50),
        },
        {
            "operation": "Parse ISO timestamp / derive month",
            "baseline": ("datetime.strptime('2025-06-15T10:30:00', '%Y-%m-%dT%H:%M:%S')", 5_000),
            "optimized": ("datetime.fromisoformat('2025-06-15T10:30:00'); '2025-06-15T10:30:00'[:7]", 10_000),
        },
    ]

    results: list[dict[str, Any]] = []
    for spec in specifications:
        row: dict[str, Any] = {"operation": spec["operation"]}
        per_operation: dict[str, float] = {}
        for label in ("baseline", "optimized"):
            statement, number = spec[label]  # type: ignore[misc]
            samples = timeit.repeat(statement, globals=namespace, number=number, repeat=5)
            seconds = min(samples)
            per_operation[label] = seconds / number
            row[label] = {
                "statement": statement,
                "number": number,
                "best_total_seconds": seconds,
                "microseconds_per_operation": per_operation[label] * 1_000_000,
            }
        row["speedup"] = per_operation["baseline"] / per_operation["optimized"]
        results.append(row)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile SalesLens engines")
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmark")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results" / "profiles")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--force-generate", action="store_true")
    parser.add_argument("--skip-microbenchmarks", action="store_true")
    args = parser.parse_args()

    data_dir = args.data_root / f"rows_{args.rows}"
    required = [data_dir / name for name in ("transactions.csv", "products.csv", "customers.csv")]
    if args.force_generate or not all(path.exists() for path in required):
        print(f"Generating {args.rows:,} rows in {data_dir}")
        generate_dataset(data_dir, args.rows, seed=args.seed)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Profiling baseline on {args.rows:,} rows...")
    baseline_summary = profile_engine(
        "baseline", lambda: baseline.analyze_directory(data_dir), args.output_dir, args.top
    )
    print(f"Profiling optimized on {args.rows:,} rows...")
    optimized_summary = profile_engine(
        "optimized", lambda: optimized.analyze_directory(data_dir), args.output_dir, args.top
    )

    parity = baseline_summary.pop("_result") == optimized_summary.pop("_result")
    if not parity:
        raise AssertionError("Profiled baseline and optimized results differ")

    payload: dict[str, Any] = {
        "rows": args.rows,
        "seed": args.seed,
        "data_dir": str(data_dir),
        "parity": "PASS",
        "baseline": baseline_summary,
        "optimized": optimized_summary,
        "call_reduction_percent": 100.0
        * (1.0 - optimized_summary["total_calls"] / baseline_summary["total_calls"]),
    }

    if not args.skip_microbenchmarks:
        print("Running timeit microbenchmarks...")
        payload["microbenchmarks"] = microbenchmarks()
        micro_json = args.output_dir / "microbenchmarks.json"
        micro_json.write_text(json.dumps(payload["microbenchmarks"], indent=2), encoding="utf-8")
        lines = ["SalesLens timeit microbenchmarks (best of 5 repeats)", ""]
        for row in payload["microbenchmarks"]:
            lines.extend(
                [
                    row["operation"],
                    f"  baseline : {row['baseline']['microseconds_per_operation']:.3f} us/op",
                    f"  optimized: {row['optimized']['microseconds_per_operation']:.3f} us/op",
                    f"  speedup  : {row['speedup']:.2f}x",
                    "",
                ]
            )
        (args.output_dir / "microbenchmarks.txt").write_text("\n".join(lines), encoding="utf-8")

    summary_path = args.output_dir / "profile_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Parity: PASS | Profile summary: {summary_path}")
    print(
        f"Function calls: baseline {baseline_summary['total_calls']:,} -> "
        f"optimized {optimized_summary['total_calls']:,} "
        f"({payload['call_reduction_percent']:.1f}% fewer)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

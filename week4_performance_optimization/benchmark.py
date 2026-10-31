#!/usr/bin/env python3
"""Repeatable baseline-vs-optimized benchmark for SalesLens.

The benchmark measures end-to-end CSV analytics, including master-data
loading, transaction parsing/validation, aggregation and result assembly.
Correctness parity is checked before timing: a faster engine that returns a
different result causes the benchmark to fail rather than silently publish a
misleading speedup.
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import platform
import statistics
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from saleslens import baseline, optimized
from saleslens.data_generator import generate_dataset

PROJECT_ROOT = Path(__file__).resolve().parent


def parse_sizes(value: str) -> list[int]:
    try:
        sizes = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes must be comma-separated integers") from exc
    if not sizes or any(size <= 0 for size in sizes):
        raise argparse.ArgumentTypeError("sizes must contain positive integers")
    return sizes


def _measure_once(function: Callable[[], Any]) -> tuple[float, float, Any]:
    gc.collect()
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    result = function()
    cpu_elapsed = time.process_time() - cpu_start
    wall_elapsed = time.perf_counter() - wall_start
    return wall_elapsed, cpu_elapsed, result


def _measure_memory(function: Callable[[], Any]) -> dict[str, int]:
    """Measure peak Python allocations with ``tracemalloc`` in a separate run."""
    gc.collect()
    if tracemalloc.is_tracing():
        tracemalloc.stop()
    tracemalloc.start()
    try:
        function()
        current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"current_bytes": int(current), "peak_bytes": int(peak)}


def _stats(values: list[float]) -> dict[str, float]:
    return {
        "runs_seconds": values,
        "min_seconds": min(values),
        "median_seconds": statistics.median(values),
        "mean_seconds": statistics.mean(values),
        "stdev_seconds": statistics.stdev(values) if len(values) > 1 else 0.0,
    }


def benchmark_size(
    rows: int,
    *,
    seed: int,
    data_root: Path,
    baseline_repeats: int,
    optimized_repeats: int,
    force_generate: bool,
) -> dict[str, Any]:
    data_dir = data_root / f"rows_{rows}"
    required = [data_dir / name for name in ("transactions.csv", "products.csv", "customers.csv")]
    if force_generate or not all(path.exists() for path in required):
        metadata = generate_dataset(data_dir, rows, seed=seed)
    else:
        metadata = {
            "transaction_rows": rows,
            "seed": seed,
            "file_sizes_bytes": {
                "products": (data_dir / "products.csv").stat().st_size,
                "customers": (data_dir / "customers.csv").stat().st_size,
                "transactions": (data_dir / "transactions.csv").stat().st_size,
            },
        }

    engines = {
        "baseline": lambda: baseline.analyze_directory(data_dir),
        "optimized": lambda: optimized.analyze_directory(data_dir),
    }

    print(f"\nDataset: {rows:,} transaction rows -> {data_dir}")
    print("Checking exact result parity before timing...")
    baseline_result = engines["baseline"]()
    optimized_result = engines["optimized"]()
    if baseline_result != optimized_result:
        different = [key for key in baseline_result if baseline_result[key] != optimized_result.get(key)]
        raise AssertionError(f"Result parity failed for keys: {different}")
    print("Parity: PASS (canonical result dictionaries are exactly equal)")

    wall_times: dict[str, list[float]] = {"baseline": [], "optimized": []}
    cpu_times: dict[str, list[float]] = {"baseline": [], "optimized": []}
    repeats = {"baseline": baseline_repeats, "optimized": optimized_repeats}

    # Interleave engines so slow system drift does not systematically favour
    # whichever implementation happens to run second.
    for round_index in range(max(repeats.values())):
        order = ("baseline", "optimized") if round_index % 2 == 0 else ("optimized", "baseline")
        for name in order:
            if round_index >= repeats[name]:
                continue
            wall, cpu, _ = _measure_once(engines[name])
            wall_times[name].append(wall)
            cpu_times[name].append(cpu)
            print(f"  {name:<10} run {round_index + 1}: {wall:.4f} s (CPU {cpu:.4f} s)")

    memory = {name: _measure_memory(engine) for name, engine in engines.items()}
    baseline_stats = _stats(wall_times["baseline"])
    optimized_stats = _stats(wall_times["optimized"])
    baseline_cpu = _stats(cpu_times["baseline"])
    optimized_cpu = _stats(cpu_times["optimized"])

    speedup_median = baseline_stats["median_seconds"] / optimized_stats["median_seconds"]
    speedup_conservative = baseline_stats["min_seconds"] / max(wall_times["optimized"])
    time_saved = 100.0 * (1.0 - optimized_stats["median_seconds"] / baseline_stats["median_seconds"])
    memory_change = 100.0 * (
        memory["optimized"]["peak_bytes"] / memory["baseline"]["peak_bytes"] - 1.0
    )

    print(
        f"Median: baseline {baseline_stats['median_seconds']:.4f} s | "
        f"optimized {optimized_stats['median_seconds']:.4f} s | speedup {speedup_median:.2f}x"
    )
    print(
        f"Peak traced memory: baseline {memory['baseline']['peak_bytes'] / 1024**2:.2f} MiB | "
        f"optimized {memory['optimized']['peak_bytes'] / 1024**2:.2f} MiB"
    )

    return {
        "rows_requested": rows,
        "data_dir": str(data_dir),
        "metadata": metadata,
        "result_summary": {
            "valid_rows": baseline_result["valid_rows"],
            "invalid_rows": baseline_result["invalid_rows"],
            "order_count": baseline_result["order_count"],
            "customer_count": baseline_result["customer_count"],
            "net_revenue": baseline_result["net_revenue"],
        },
        "parity": "PASS",
        "baseline": {
            "wall": baseline_stats,
            "cpu": baseline_cpu,
            "tracemalloc": memory["baseline"],
        },
        "optimized": {
            "wall": optimized_stats,
            "cpu": optimized_cpu,
            "tracemalloc": memory["optimized"],
        },
        "speedup_median": speedup_median,
        "speedup_conservative_min_vs_max": speedup_conservative,
        "median_time_saved_percent": time_saved,
        "peak_memory_change_percent": memory_change,
    }


def optimized_only_check(rows: int, *, seed: int, data_root: Path, force_generate: bool) -> dict[str, Any]:
    """Run a larger optimized-only scalability check."""
    data_dir = data_root / f"rows_{rows}"
    required = [data_dir / name for name in ("transactions.csv", "products.csv", "customers.csv")]
    if force_generate or not all(path.exists() for path in required):
        metadata = generate_dataset(data_dir, rows, seed=seed)
    else:
        metadata = {"transaction_rows": rows, "seed": seed}
    wall, cpu, result = _measure_once(lambda: optimized.analyze_directory(data_dir))
    memory = _measure_memory(lambda: optimized.analyze_directory(data_dir))
    print(f"\nOptimized-only scalability check: {rows:,} rows in {wall:.4f} s")
    return {
        "rows_requested": rows,
        "data_dir": str(data_dir),
        "metadata": metadata,
        "wall_seconds": wall,
        "cpu_seconds": cpu,
        "tracemalloc": memory,
        "result_summary": {
            "valid_rows": result["valid_rows"],
            "order_count": result["order_count"],
            "net_revenue": result["net_revenue"],
        },
    }


def write_outputs(payload: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "benchmark_results.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    csv_path = output_dir / "benchmark_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rows", "baseline_median_s", "optimized_median_s", "speedup_median_x",
                "speedup_conservative_x", "time_saved_percent",
                "baseline_peak_memory_mib", "optimized_peak_memory_mib", "memory_change_percent",
            ]
        )
        for row in payload["benchmarks"]:
            writer.writerow(
                [
                    row["rows_requested"],
                    f"{row['baseline']['wall']['median_seconds']:.6f}",
                    f"{row['optimized']['wall']['median_seconds']:.6f}",
                    f"{row['speedup_median']:.3f}",
                    f"{row['speedup_conservative_min_vs_max']:.3f}",
                    f"{row['median_time_saved_percent']:.2f}",
                    f"{row['baseline']['tracemalloc']['peak_bytes'] / 1024**2:.3f}",
                    f"{row['optimized']['tracemalloc']['peak_bytes'] / 1024**2:.3f}",
                    f"{row['peak_memory_change_percent']:.2f}",
                ]
            )

    md_path = output_dir / "benchmark_summary.md"
    lines = [
        "# SalesLens benchmark summary",
        "",
        f"Generated: {payload['environment']['recorded_at_utc']}",
        f"Python: {payload['environment']['python_version']}",
        "",
        "| Rows | Baseline median | Optimized median | Speedup | Time saved | Baseline peak | Optimized peak |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in payload["benchmarks"]:
        lines.append(
            f"| {row['rows_requested']:,} | {row['baseline']['wall']['median_seconds']:.4f} s | "
            f"{row['optimized']['wall']['median_seconds']:.4f} s | {row['speedup_median']:.2f}x | "
            f"{row['median_time_saved_percent']:.1f}% | "
            f"{row['baseline']['tracemalloc']['peak_bytes'] / 1024**2:.2f} MiB | "
            f"{row['optimized']['tracemalloc']['peak_bytes'] / 1024**2:.2f} MiB |"
        )
    if payload.get("optimized_only"):
        item = payload["optimized_only"]
        lines.extend(
            [
                "",
                f"Optimized-only scalability check: {item['rows_requested']:,} rows in "
                f"{item['wall_seconds']:.4f} s; peak traced memory "
                f"{item['tracemalloc']['peak_bytes'] / 1024**2:.2f} MiB.",
            ]
        )
    lines.extend(
        [
            "",
            "Parity was checked by exact equality of the canonical result dictionaries before timing.",
            "Memory is peak Python allocation measured by `tracemalloc` in separate runs.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote:\n- {json_path}\n- {csv_path}\n- {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark SalesLens baseline vs optimized")
    parser.add_argument("--sizes", type=parse_sizes, default=parse_sizes("2000,5000,10000"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--baseline-repeats", type=int, default=3)
    parser.add_argument("--optimized-repeats", type=int, default=5)
    parser.add_argument("--data-root", type=Path, default=PROJECT_ROOT / "data" / "benchmark")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "results")
    parser.add_argument("--force-generate", action="store_true")
    parser.add_argument("--optimized-only-size", type=int, default=0)
    args = parser.parse_args()

    if args.baseline_repeats <= 0 or args.optimized_repeats <= 0:
        parser.error("repeat counts must be positive")

    payload: dict[str, Any] = {
        "environment": {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor() or "not reported",
            "cpu_count": os.cpu_count(),
            "executable": sys.executable,
        },
        "configuration": {
            "sizes": args.sizes,
            "seed": args.seed,
            "baseline_repeats": args.baseline_repeats,
            "optimized_repeats": args.optimized_repeats,
            "timing": "time.perf_counter wall time; time.process_time CPU time",
            "memory": "tracemalloc peak Python allocations in separate runs",
        },
        "benchmarks": [
            benchmark_size(
                rows,
                seed=args.seed,
                data_root=args.data_root,
                baseline_repeats=args.baseline_repeats,
                optimized_repeats=args.optimized_repeats,
                force_generate=args.force_generate,
            )
            for rows in args.sizes
        ],
    }
    if args.optimized_only_size:
        payload["optimized_only"] = optimized_only_check(
            args.optimized_only_size,
            seed=args.seed,
            data_root=args.data_root,
            force_generate=args.force_generate,
        )

    write_outputs(payload, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

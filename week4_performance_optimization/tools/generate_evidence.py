#!/usr/bin/env python3
"""Generate reproducible Week 4 report evidence and PNG figures.

This reporting utility executes the real test, benchmark, profiling and demo
commands; stores raw transcripts under ``docs/evidence``; and renders charts
or terminal-style figures for the Word report.  It is not part of the runtime
SalesLens API.

Install optional evidence dependencies and run from the project root::

    pip install -r requirements-dev.txt -r requirements-evidence.txt
    python tools/generate_evidence.py

Use ``--reuse-results`` to redraw figures from existing benchmark/profile
outputs without repeating the expensive baseline runs.
"""

from __future__ import annotations

import argparse
import ast
import json
import platform
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence"
FIGURES = EVIDENCE / "figures"
RESULTS = ROOT / "results"
PROFILES = RESULTS / "profiles"

FONT_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_SANS_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(path: str, size: int):
    """Load a font with cross-platform fallbacks for optional evidence use."""
    requested = Path(path)
    candidates = [requested]
    try:
        import matplotlib as mpl

        candidates.append(Path(mpl.__file__).parent / "mpl-data" / "fonts" / "ttf" / requested.name)
    except Exception:
        pass
    if "Mono" in requested.name:
        candidates.extend(Path(p) for p in ("/Library/Fonts/Menlo.ttc", "C:/Windows/Fonts/consola.ttf"))
    else:
        candidates.extend(Path(p) for p in ("/Library/Fonts/Arial.ttf", "C:/Windows/Fonts/arial.ttf"))
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def run_command(name: str, args: list[str], *, timeout: int = 1800) -> str:
    """Run a real project command and save a labelled transcript."""
    print(f"\n>>> {name}: {' '.join(args)}", flush=True)
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    display = ["python" if arg == sys.executable else arg for arg in args]
    transcript = f"$ {' '.join(display)}\n{result.stdout}{result.stderr}[exit_code={result.returncode}]\n"
    print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {name}")
    return transcript


def save_text(name: str, content: str) -> Path:
    path = EVIDENCE / name
    path.write_text(content, encoding="utf-8")
    return path


def render_terminal(title: str, lines: list[str], filename: str, accent: str = "#2f9e44") -> Path:
    wrapped: list[str] = []
    for raw in lines:
        wrapped.extend(textwrap.wrap(raw, width=112, replace_whitespace=False, drop_whitespace=False) or [""])

    width = 1680
    line_height = 27
    top = 88
    height = top + max(1, len(wrapped)) * line_height + 34
    image = Image.new("RGB", (width, height), "#101418")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 58), fill="#242b33")
    for index, color in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        x = 24 + index * 30
        draw.ellipse((x, 19, x + 18, 37), fill=color)
    draw.text((122, 16), title, font=font(FONT_MONO_BOLD, 20), fill="#e6edf3")
    draw.rectangle((0, 58, width, 64), fill=accent)

    mono = font(FONT_MONO, 19)
    y = top
    for line in wrapped:
        color = "#d6deeb"
        lowered = line.lower()
        if line.startswith("$"):
            color = "#8ce99a"
        elif "passed" in lowered or "pass" in lowered or "speedup" in lowered:
            color = "#69db7c"
        elif "baseline" in lowered:
            color = "#ffa8a8"
        elif "optimized" in lowered:
            color = "#a9e34b"
        draw.text((28, y), line, font=mono, fill=color)
        y += line_height

    path = FIGURES / filename
    image.save(path, optimize=True)
    return path


def _box(draw: ImageDraw.ImageDraw, xy, title: str, body: str, fill: str, outline: str) -> None:
    draw.rounded_rectangle(xy, radius=22, fill=fill, outline=outline, width=3)
    x1, y1, _x2, _y2 = xy
    draw.text((x1 + 24, y1 + 20), title, font=font(FONT_SANS_BOLD, 26), fill="#153a63")
    y = y1 + 66
    for line in body.splitlines():
        draw.text((x1 + 24, y), line, font=font(FONT_SANS, 21), fill="#334155")
        y += 31


def _arrow(draw: ImageDraw.ImageDraw, start, end, color: str = "#64748b") -> None:
    draw.line((start, end), fill=color, width=5)
    x, y = end
    draw.polygon([(x, y), (x - 16, y - 9), (x - 16, y + 9)], fill=color)


def draw_pipeline() -> Path:
    width, height = 1680, 980
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "SalesLens performance-optimization pipeline", font=font(FONT_SANS_BOLD, 36), fill="#153a63")

    _box(draw, (55, 150, 430, 360), "Deterministic data", "seeded generator\nproducts/customers\ntransaction line items", "#fef3c7", "#d97706")
    _box(draw, (565, 150, 940, 360), "Baseline engine", "linear searches\nlist buckets / multi-pass\noriginal implementation", "#fee2e2", "#dc2626")
    _box(draw, (1075, 150, 1450, 360), "Optimized engine", "dict indexes / sets\nCounter / one pass\nsame public API", "#dcfce7", "#16a34a")
    _arrow(draw, (430, 255), (565, 255))
    _arrow(draw, (940, 255), (1075, 255))

    _box(draw, (250, 500, 675, 715), "Canonical result", "same keys, ordering,\nrounding and tie-breaks", "#dbeafe", "#2563eb")
    _box(draw, (805, 500, 1230, 715), "Verification", "hand-checked oracle\n17 automated tests\nexact parity checks", "#ede9fe", "#7c3aed")
    _box(draw, (1250, 500, 1625, 715), "Evidence", "benchmarks\ncProfile / timeit\ntracemalloc", "#e0f2fe", "#0284c7")
    # Simple vertical connectors
    draw.line((755, 360, 460, 500), fill="#64748b", width=5)
    draw.line((1260, 360, 500, 500), fill="#64748b", width=3)
    _arrow(draw, (675, 608), (805, 608))
    _arrow(draw, (1230, 608), (1250, 608))

    draw.rounded_rectangle((55, 800, 1625, 890), radius=16, fill="#eef2f7", outline="#9fb3c8", width=2)
    draw.text(
        (80, 830),
        "Correctness is a benchmark gate: timing is not accepted unless both engines return exactly the same result.",
        font=font(FONT_SANS_BOLD, 22),
        fill="#153a63",
    )
    path = FIGURES / "fig01_pipeline_architecture.png"
    image.save(path, optimize=True)
    return path


def draw_optimization_map() -> Path:
    width, height = 1680, 1080
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((55, 35), "Profile hotspot -> optimization applied", font=font(FONT_SANS_BOLD, 36), fill="#153a63")

    rows = [
        ("_find_by_id scans masters", "load dict index once; O(1) lookup", "O(n x m) -> O(n+m)"),
        ("list buckets searched per row", "dict / defaultdict / Counter", "O(n x k) -> O(n)"),
        ("list distinct + list.count", "sets + Counter", "quadratic scans removed"),
        ("multiple full passes", "single streaming pass", "fewer calls & less memory"),
        ("strptime + strftime per row", "fromisoformat once + month slice", "less parsing overhead"),
        ("sort/select all for top 10", "heapq.nlargest with tie key", "O(k log 10) selection"),
    ]
    y = 130
    draw.rounded_rectangle((55, y, 500, y + 58), radius=12, fill="#fee2e2", outline="#dc2626", width=2)
    draw.text((78, y + 15), "Baseline hotspot", font=font(FONT_SANS_BOLD, 22), fill="#991b1b")
    draw.rounded_rectangle((565, y, 1125, y + 58), radius=12, fill="#dcfce7", outline="#16a34a", width=2)
    draw.text((588, y + 15), "Optimized replacement", font=font(FONT_SANS_BOLD, 22), fill="#14532d")
    draw.rounded_rectangle((1190, y, 1625, y + 58), radius=12, fill="#dbeafe", outline="#2563eb", width=2)
    draw.text((1213, y + 15), "Complexity effect", font=font(FONT_SANS_BOLD, 22), fill="#1e3a8a")
    y += 82
    for left, middle, right in rows:
        for x1, x2, text, fill in [
            (55, 500, left, "#fff7ed"),
            (565, 1125, middle, "#f0fdf4"),
            (1190, 1625, right, "#eff6ff"),
        ]:
            draw.rounded_rectangle((x1, y, x2, y + 88), radius=14, fill=fill, outline="#cbd5e1", width=2)
            lines = textwrap.wrap(text, width=31)
            ty = y + 15
            for line in lines:
                draw.text((x1 + 20, ty), line, font=font(FONT_SANS, 20), fill="#1f2937")
                ty += 27
        _arrow(draw, (500, y + 44), (565, y + 44), "#94a3b8")
        y += 112

    path = FIGURES / "fig03_optimization_map.png"
    image.save(path, optimize=True)
    return path


def draw_benchmark_charts(benchmark: dict) -> tuple[Path, Path]:
    rows = [item["rows_requested"] for item in benchmark["benchmarks"]]
    baseline = [item["baseline"]["wall"]["median_seconds"] for item in benchmark["benchmarks"]]
    optimized = [item["optimized"]["wall"]["median_seconds"] for item in benchmark["benchmarks"]]
    speedups = [item["speedup_median"] for item in benchmark["benchmarks"]]
    baseline_mem = [item["baseline"]["tracemalloc"]["peak_bytes"] / 1024**2 for item in benchmark["benchmarks"]]
    optimized_mem = [item["optimized"]["tracemalloc"]["peak_bytes"] / 1024**2 for item in benchmark["benchmarks"]]
    labels = [f"{row:,}" for row in rows]
    x = range(len(rows))
    width = 0.38

    fig, ax = plt.subplots(figsize=(10, 5.6))
    bars1 = ax.bar([i - width / 2 for i in x], baseline, width=width, label="Baseline", color="#dc2626")
    bars2 = ax.bar([i + width / 2 for i in x], optimized, width=width, label="Optimized", color="#16a34a")
    ax.set_yscale("log")
    ax.set_xticks(list(x), labels)
    ax.set_xlabel("Transaction rows")
    ax.set_ylabel("Median wall time (seconds, log scale)")
    ax.set_title("End-to-end runtime: baseline vs optimized")
    ax.grid(axis="y", which="both", alpha=0.25)
    ax.legend()
    for bars in (bars1, bars2):
        for bar in bars:
            ax.annotate(f"{bar.get_height():.3f}s", (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom", fontsize=8)
    runtime_path = FIGURES / "fig04_runtime_comparison.png"
    fig.tight_layout()
    fig.savefig(runtime_path, dpi=180)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    bars = axes[0].bar(labels, speedups, color="#2563eb")
    axes[0].set_xlabel("Transaction rows")
    axes[0].set_ylabel("Median speedup (x)")
    axes[0].set_title("Speedup grows with scale")
    axes[0].grid(axis="y", alpha=0.25)
    for bar in bars:
        axes[0].annotate(f"{bar.get_height():.1f}x", (bar.get_x() + bar.get_width() / 2, bar.get_height()), ha="center", va="bottom", fontsize=9)

    axes[1].bar([i - width / 2 for i in x], baseline_mem, width=width, label="Baseline", color="#dc2626")
    axes[1].bar([i + width / 2 for i in x], optimized_mem, width=width, label="Optimized", color="#16a34a")
    axes[1].set_xticks(list(x), labels)
    axes[1].set_xlabel("Transaction rows")
    axes[1].set_ylabel("Peak traced memory (MiB)")
    axes[1].set_title("tracemalloc peak memory")
    axes[1].grid(axis="y", alpha=0.25)
    axes[1].legend()

    combined_path = FIGURES / "fig05_speedup_memory.png"
    fig.tight_layout()
    fig.savefig(combined_path, dpi=180)
    plt.close(fig)
    return runtime_path, combined_path


def project_metrics() -> str:
    lines = ["SalesLens project metrics (AST-based)", ""]
    totals = {"files": 0, "lines": 0, "functions": 0, "classes": 0}
    for group in ("saleslens", "tests", "tools", "root scripts"):
        lines.append(f"[{group}]")
        group_totals = {"lines": 0, "functions": 0, "classes": 0, "files": 0}
        paths = (
            [ROOT / "benchmark.py", ROOT / "run.py"]
            if group == "root scripts"
            else sorted((ROOT / group).rglob("*.py"))
        )
        for path in paths:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
            functions = sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
            classes = sum(isinstance(node, ast.ClassDef) for node in ast.walk(tree))
            line_count = len(text.splitlines())
            lines.append(f"  {path.relative_to(ROOT)}: {line_count} lines, {functions} functions, {classes} classes")
            group_totals["lines"] += line_count
            group_totals["functions"] += functions
            group_totals["classes"] += classes
            group_totals["files"] += 1
        lines.append(
            f"  TOTAL {group}: {group_totals['files']} files, {group_totals['lines']} lines, "
            f"{group_totals['functions']} functions, {group_totals['classes']} classes"
        )
        lines.append("")
        for key in totals:
            totals[key] += group_totals[key]
    lines.append(
        f"PROJECT TOTAL: {totals['files']} Python files, {totals['lines']} lines, "
        f"{totals['functions']} functions, {totals['classes']} classes"
    )
    return "\n".join(lines) + "\n"


def selected_profile_lines(path: Path, max_lines: int = 30) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if "sorted by tottime" in line), 0)
    selected = []
    for line in lines[start:]:
        # Shorten machine-specific prefixes only in the rendered figure.  The
        # raw profile text remains untouched for auditability.
        display_line = line.replace(f"{ROOT}/", "").replace("/usr/local/lib/python3.13/", "python3.13/")
        if display_line.strip() and not display_line.startswith("   ncalls"):
            selected.append(display_line)
        elif display_line.startswith("   ncalls"):
            selected.append(display_line)
        if len(selected) >= max_lines:
            break
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Week 4 evidence")
    parser.add_argument("--reuse-results", action="store_true", help="do not rerun benchmark/profile commands")
    parser.add_argument("--profile-rows", type=int, default=10_000)
    parser.add_argument("--optimized-only-size", type=int, default=100_000)
    args = parser.parse_args()

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    save_text(
        "environment.txt",
        "\n".join(
            [
                f"Python: {platform.python_version()} ({platform.python_implementation()})",
                f"Platform: {platform.platform()}",
                f"Machine: {platform.machine()}",
                f"Processor: {platform.processor() or 'not reported'}",
            ]
        )
        + "\n",
    )

    if args.reuse_results:
        benchmark_text = "Benchmark results reused from results/benchmark_results.json\n"
        profiling_text = "Profiling results reused from results/profiles/\n"
    else:
        benchmark_text = run_command(
            "benchmark",
            [
                sys.executable,
                "benchmark.py",
                "--sizes",
                "2000,5000,10000",
                "--baseline-repeats",
                "3",
                "--optimized-repeats",
                "5",
                "--optimized-only-size",
                str(args.optimized_only_size),
                "--force-generate",
            ],
        )
        profiling_text = run_command(
            "profiling",
            [sys.executable, "tools/run_profiling.py", "--rows", str(args.profile_rows)],
        )

    save_text("benchmark_run.txt", benchmark_text)
    save_text("profiling_run.txt", profiling_text)

    tests_text = run_command("tests", [sys.executable, "-m", "pytest", "-v"])
    save_text("pytest_verbose.txt", tests_text)

    demo_text = run_command(
        "demo",
        [
            sys.executable,
            "run.py",
            "--engine",
            "optimized",
            "--data-dir",
            "data/sample",
            "--generate",
            "--rows",
            "5000",
            "--output",
            "results/sample_result.json",
        ],
    )
    save_text("demo_output.txt", demo_text)
    save_text("project_metrics.txt", project_metrics())

    benchmark = json.loads((RESULTS / "benchmark_results.json").read_text(encoding="utf-8"))
    draw_pipeline()
    draw_optimization_map()
    draw_benchmark_charts(benchmark)

    render_terminal(
        "Baseline cProfile (tottime view)",
        selected_profile_lines(PROFILES / "baseline_cprofile.txt"),
        "fig02_baseline_cprofile.png",
        "#e03131",
    )
    render_terminal(
        "Optimized cProfile (tottime view)",
        selected_profile_lines(PROFILES / "optimized_cprofile.txt"),
        "fig07_optimized_cprofile.png",
        "#2f9e44",
    )

    benchmark_summary = (RESULTS / "benchmark_summary.md").read_text(encoding="utf-8").splitlines()
    profile_summary = json.loads((PROFILES / "profile_summary.json").read_text(encoding="utf-8"))
    benchmark_lines = [
        "$ python benchmark.py --sizes 2000,5000,10000 --baseline-repeats 3 --optimized-repeats 5",
        "",
        *benchmark_summary,
        "",
        f"cProfile calls at {profile_summary['rows']:,} rows: "
        f"baseline {profile_summary['baseline']['total_calls']:,} -> "
        f"optimized {profile_summary['optimized']['total_calls']:,} "
        f"({profile_summary['call_reduction_percent']:.1f}% fewer)",
    ]
    render_terminal("Benchmark and call-count summary", benchmark_lines, "fig06_benchmark_summary.png", "#1971c2")

    test_lines = tests_text.splitlines()
    selected_tests = test_lines if len(test_lines) <= 26 else test_lines[:12] + ["..."] + test_lines[-14:]
    render_terminal("Automated correctness and parity tests", selected_tests, "fig08_tests_parity.png", "#7048e8")
    render_terminal("Optimized demo execution", demo_text.splitlines(), "fig09_demo_output.png", "#2f9e44")

    print("\nEvidence written to", EVIDENCE)
    for path in sorted(FIGURES.glob("*.png")):
        print("-", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

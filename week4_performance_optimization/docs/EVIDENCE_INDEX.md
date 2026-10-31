# Evidence Index — Week 4

This index connects every headline claim to submitted code, automated tests and
raw execution artefacts. Figure numbers match their order in the Word report.

## Figure evidence

| Figure | Claim supported | Source artefact |
|---|---|---|
| Fig. 1 — Pipeline architecture | Same generated data flows through both engines into one canonical result and verification gate | `docs/evidence/figures/fig01_pipeline_architecture.png` |
| Fig. 2 — Baseline cProfile | 13,833,156 calls; `_find_by_id`, co-purchase, `list.count` and bucket scans dominate | `results/profiles/baseline_cprofile.txt`; `fig02_baseline_cprofile.png` |
| Fig. 3 — Optimization map | Each baseline hotspot has a specific data-structure/algorithm replacement | `docs/evidence/figures/fig03_optimization_map.png` |
| Fig. 4 — Runtime comparison | Multi-scale median wall time, log scale | `results/benchmark_results.json`; `fig04_runtime_comparison.png` |
| Fig. 5 — Speedup/memory | Speedup grows with rows while traced peak memory falls | `results/benchmark_results.json`; `fig05_speedup_memory.png` |
| Fig. 6 — Benchmark summary | Exact recorded medians, memory and call reduction | `results/benchmark_summary.md`; `results/profiles/profile_summary.json`; `fig06_benchmark_summary.png` |
| Fig. 7 — Optimized cProfile | 322,723 calls; remaining time is CSV + single-pass loop | `results/profiles/optimized_cprofile.txt`; `fig07_optimized_cprofile.png` |
| Fig. 8 — Tests/parity | 17 automated tests pass | `docs/evidence/pytest_verbose.txt`; `tests/`; `fig08_tests_parity.png` |
| Fig. 9 — Demo | Optimized CLI produces the expected 5,000-row analytics and JSON | `docs/evidence/demo_output.txt`; `results/sample_result.json`; `fig09_demo_output.png` |

## Requirement-to-evidence traceability

| Week 4 requirement | Implementation evidence | Verification evidence | Execution evidence |
|---|---|---|---|
| Develop a data/computational application | `saleslens/data_generator.py`, `baseline.py`, `optimized.py`, `run.py` | Hand-checked dataset in `tests/test_correctness.py` | Fig. 1 and Fig. 9 |
| Establish baseline performance | Original engine preserved in `saleslens/baseline.py` | Benchmark parity gate in `benchmark.py` | `results/benchmark_results.json`; Fig. 4 |
| Profile with cProfile/timeit or equivalent | `tools/run_profiling.py` | Profiled engines assert result parity | `results/profiles/*.txt`, `microbenchmarks.txt`; Fig. 2 and Fig. 7 |
| Identify bottlenecks | `_find_by_id`, `_add_to_bucket`, `_distinct_add`, `_count_duplicate_ids`, `_co_purchase_pairs` | Complexity analysis in `docs/PERFORMANCE_ANALYSIS.md` §4–5 | Baseline cProfile top entries; Fig. 2 |
| Apply algorithmic/data-structure optimizations | Dict indexes, sets, `Counter`, `defaultdict`, one pass, `heapq.nlargest` in `optimized.py` | Same API/canonical result; 17 tests | Fig. 3 and Fig. 5 |
| Compare before/after time and resources | Wall/CPU time, repeats and `tracemalloc` in `benchmark.py` | JSON/CSV/Markdown preserve every run | `results/benchmark_*`; Fig. 4–6 |
| Maintain functionality/accuracy | Shared result contract and deterministic ties | Hand oracle + exact generated-data parity + benchmark gate | Fig. 8 |
| Self-contained ZIP/no external inputs | Seeded generator + included sample data; runtime has no dependencies | Fresh extraction test/demo verification during packaging | `data/sample/`, generator tests |

## Source locations for report listings

| Listing subject | Submitted location |
|---|---|
| Baseline master search and bucket scan | `saleslens/baseline.py`, `_find_by_id`, `_add_to_bucket`, `_distinct_add` |
| Baseline quadratic duplicate detection | `saleslens/baseline.py`, `_count_duplicate_ids` |
| Baseline list-backed co-purchase grouping | `saleslens/baseline.py`, `_co_purchase_pairs` |
| Optimized master indexing | `saleslens/optimized.py`, `_load_products`, `_load_customers` |
| Optimized streaming analyzer | `saleslens/optimized.py`, `analyze_dataset` |
| Deterministic top-N tie handling | `saleslens/optimized.py`, `_DescendingString` and top-N block |
| Generated-data parity test | `tests/test_parity_and_generator.py`, `test_generated_dataset_parity` |
| Hand-calculated oracle test | `tests/test_correctness.py`, `test_hand_checked_metrics` |
| Parity-gated timing/memory harness | `benchmark.py`, `_measure_once`, `_measure_memory`, `benchmark_size` |
| cProfile/timeit harness | `tools/run_profiling.py`, `profile_engine`, `microbenchmarks` |

## Raw outputs

| File | Meaning |
|---|---|
| `results/benchmark_results.json` | Environment, configuration, every timed run, CPU time and memory |
| `results/benchmark_summary.csv` | Machine-readable before/after summary |
| `results/benchmark_summary.md` | Human-readable generated summary |
| `results/profiles/baseline_cprofile.txt` | Baseline `tottime` and cumulative profile views |
| `results/profiles/optimized_cprofile.txt` | Optimized `tottime` and cumulative profile views |
| `results/profiles/profile_summary.json` | Call counts, profile totals and microbenchmark payload |
| `results/profiles/microbenchmarks.txt` | Isolated `timeit` comparisons |
| `docs/evidence/pytest_verbose.txt` | Actual test transcript |
| `docs/evidence/demo_output.txt` | Actual optimized demo transcript |
| `docs/evidence/project_metrics.txt` | AST file/line/function/class counts |
| `docs/evidence/environment.txt` | Python/platform summary |

# Week 4 — Performance Optimization in Python Applications

## SalesLens: baseline vs. optimized retail transaction analytics

This project is a complete, reproducible performance-engineering case study.
SalesLens reads product, customer and transaction CSV files and produces
revenue, customer, product and co-purchase analytics. The same application is
implemented twice:

| Engine | File | Technique |
|---|---|---|
| **Original / baseline** | `saleslens/baseline.py` | Linear master searches, list-backed buckets, repeated scans, `list.count` duplicate detection |
| **Optimized** | `saleslens/optimized.py` | Dictionary indexes, one streaming pass, `defaultdict`/`Counter`/sets, `heapq.nlargest` |

The optimized engine is not allowed to “win” by changing the answer: both
engines expose the same API and the benchmark checks exact equality of the full
canonical result dictionary before timing.

## Headline results

Measured end to end on deterministic generated datasets (seed 42; baseline =
3 interleaved repeats, optimized = 5; median wall time):

| Transaction rows | Baseline | Optimized | Speedup | Time saved | Baseline peak memory | Optimized peak memory |
|---:|---:|---:|---:|---:|---:|---:|
| 2,000 | 0.4045 s | 0.0211 s | **19.16×** | 94.8% | 4.31 MiB | 1.91 MiB |
| 5,000 | 1.7251 s | 0.0431 s | **40.05×** | 97.5% | 8.68 MiB | 3.46 MiB |
| 10,000 | 6.1780 s | 0.0774 s | **79.87×** | 98.7% | 15.76 MiB | 5.83 MiB |

At 10,000 rows, cProfile function calls fell from **13,833,156** to
**322,723** (**97.7% fewer**). A separate optimized-only scalability check
processed **100,000 rows in 0.8014 s**. Memory is `tracemalloc` peak Python
allocation, measured in separate runs so tracing does not contaminate timing.

![Runtime comparison](docs/evidence/figures/fig04_runtime_comparison.png)

![Speedup and memory](docs/evidence/figures/fig05_speedup_memory.png)

## 1. Quick start

Requirements: Python 3.10+. The application uses only the standard library.

```bash
# Run the included 5,000-row sample with the optimized engine
python run.py --engine optimized --data-dir data/sample

# Run the original implementation on exactly the same data
python run.py --engine baseline --data-dir data/sample

# Generate a fresh deterministic dataset and run it
python run.py --engine optimized --data-dir data/mydata --generate --rows 10000 --seed 42

# Save the canonical analytics dictionary as JSON
python run.py --engine optimized --data-dir data/sample --output results/sample_result.json
```

Expected sample headline:

```text
Rows read: 5000 (valid 4995, invalid 5)
Orders: 2821 | Customers: 1697 | Units: 8518
Net revenue: INR 49,797,267.12 | Average order value: INR 17,652.35
```

## 2. Tests, benchmark and profiling

```bash
pip install -r requirements-dev.txt

# 17 correctness, parity and generator tests
python -m pytest -v

# Reproduce the recorded multi-scale benchmark
python benchmark.py \
  --sizes 2000,5000,10000 \
  --baseline-repeats 3 \
  --optimized-repeats 5 \
  --optimized-only-size 100000 \
  --force-generate

# Reproduce cProfile output and timeit microbenchmarks
python tools/run_profiling.py --rows 10000

# Optional: regenerate report figures/transcripts from real executions
pip install -r requirements-evidence.txt
python tools/generate_evidence.py --reuse-results
```

Benchmark outputs are written to `results/`; profile outputs are written to
`results/profiles/`. Generated benchmark datasets are written under
`data/benchmark/` and are intentionally excluded from Git by `.gitignore`:
they can be recreated deterministically from the seed.

## 3. What SalesLens computes

For every supported dataset, both engines return the same canonical dictionary
containing:

- rows read, valid rows and invalid rows;
- distinct orders and customers;
- total units, gross revenue, discount amount and net revenue;
- average order value;
- revenue by month, category and region, plus category revenue shares;
- top 10 products by revenue and top 10 customers by spend;
- repeat-customer count/rate and high-value customer count;
- duplicate transaction IDs and extra duplicate rows;
- top 10 products bought together in the same order;
- best revenue month.

Ties are deterministic: revenue/count descending, then ID/month ascending.
Monetary outputs are rounded to two decimals in the canonical result.

## 4. Input files

Each dataset directory contains:

```text
products.csv
  product_id,product_name,category,unit_price

customers.csv
  customer_id,customer_name,region

transactions.csv
  transaction_id,order_id,timestamp,customer_id,product_id,quantity,discount_percent
```

Timestamps use `YYYY-MM-DDTHH:MM:SS`. A transaction is counted as invalid and
excluded when a required field is missing/malformed, the timestamp or numbers
cannot be parsed, quantity is not positive, discount is outside 0–90%, the
unit price is invalid/negative, or the product/customer does not exist.
Duplicate master IDs use the first record, matching the baseline.

The generator creates 500 products and 3,000 customers by default, realistic
popularity skew, orders with one to four line items, approximately 0.2%
duplicate transaction IDs, and a 0.1% invalid-row tail for large files.

## 5. Where the time went

The baseline cProfile at 10,000 rows shows the expected hotspots:

| Baseline hotspot | Calls | Internal time (`tottime`) | Interpretation |
|---|---:|---:|---|
| `_find_by_id` | 19,988 | 2.461 s | Product/customer list searched for every row |
| `_co_purchase_pairs` | 1 | 2.203 s | List-backed order-group and pair searches |
| `dict.get` | 13,172,264 | 2.105 s | Mostly key probes inside the linear searches |
| `list.count` | 9,990 | 1.324 s | Full ID list rescanned once per transaction |
| `_distinct_add` | 40,002 | 0.556 s | List membership used as a set substitute |
| `_customer_order_counts` | 1 | 0.511 s | Nested customer/order lists |
| `_add_to_bucket` | 49,950 | 0.501 s | Five list-bucket searches per valid row |

The complete before/after profiles are in
`results/profiles/baseline_cprofile.txt` and
`results/profiles/optimized_cprofile.txt`.

## 6. Optimizations applied

1. **Index master data once.** Products/customers become dictionaries, so row
   enrichment changes from repeated list scans to expected O(1) lookup.
2. **Aggregate with hash-based containers.** Dictionaries, `defaultdict` and
   `Counter` replace list bucket searches.
3. **Stream in one pass.** Totals, monthly/category/region revenue, product
   and customer stats, distinct values, duplicate counts and order groups are
   updated while each CSV row is visited once.
4. **Use sets for distinct/order membership.** This removes list-membership
   and `list.count` quadratic behaviour.
5. **Group co-purchases with `defaultdict(set)`** and use
   `itertools.combinations` on small per-order product sets.
6. **Use the standard CSV reader and faster date validation.**
   `datetime.fromisoformat` validates once; the month is the `YYYY-MM` prefix.
7. **Select top 10 with `heapq.nlargest`** while preserving deterministic
   revenue-descending/ID-ascending ties.
8. **Avoid retaining enriched transaction dictionaries.** The optimized engine
   keeps indexes and aggregates, not a second full copy of every row.
9. **Build report text with a list and one `join`** instead of repeated string
   concatenation (a minor, safe cleanup; not the source of the main speedup).

## 7. Project structure

```text
week4_performance_optimization/
├── run.py                         # CLI for either engine
├── benchmark.py                   # parity-gated benchmark harness
├── saleslens/
│   ├── data_generator.py          # deterministic synthetic datasets
│   ├── baseline.py                # ORIGINAL implementation (preserved)
│   └── optimized.py               # OPTIMIZED implementation
├── tests/                         # 17 automated correctness/parity items
├── tools/
│   ├── run_profiling.py           # cProfile + timeit evidence
│   └── generate_evidence.py       # figures and transcripts
├── data/sample/                   # included 5,000-row sample dataset
├── results/
│   ├── benchmark_results.json
│   ├── benchmark_summary.csv/.md
│   ├── sample_result.json
│   └── profiles/
├── docs/
│   ├── PERFORMANCE_ANALYSIS.md    # detailed engineering analysis
│   ├── EVIDENCE_INDEX.md          # claim -> code -> test -> output map
│   ├── WORK_LOG.md                # phases, outputs and problems
│   └── evidence/figures/          # 9 figures embedded in the Word report
├── requirements.txt               # runtime: none
├── requirements-dev.txt           # pytest
├── requirements-evidence.txt      # Pillow + matplotlib (figures only)
└── SUBMISSION_DESCRIPTION.txt
```

## 8. Documentation map

- [`docs/PERFORMANCE_ANALYSIS.md`](docs/PERFORMANCE_ANALYSIS.md) — full
  methodology, bottleneck analysis, complexity, results and limitations.
- [`docs/EVIDENCE_INDEX.md`](docs/EVIDENCE_INDEX.md) — every figure and each
  task requirement mapped to code, tests and raw outputs.
- [`docs/WORK_LOG.md`](docs/WORK_LOG.md) — work phases and problems resolved.
- [`results/benchmark_summary.md`](results/benchmark_summary.md) — generated
  benchmark table.
- [`results/profiles/microbenchmarks.txt`](results/profiles/microbenchmarks.txt)
  — isolated `timeit` comparisons.

## 9. Interpretation and limitations

- Absolute seconds are machine-dependent; the recorded run used CPython
  3.13.16 on Linux x86_64 with 2 CPUs reported. The important evidence is the
  same-machine paired comparison, repeated runs and scaling trend.
- cProfile adds overhead, so profile time is used to locate hotspots, not to
  claim the headline speedup.
- The optimized indexes and per-customer/order sets use memory. In the tested
  datasets this is more than offset by not retaining all enriched rows, giving
  a 63.0% lower traced peak at 10,000 rows.
- Complexity is expected-case for hash containers. Very large individual
  orders would still make co-purchase pair enumeration grow quadratically in
  the number of distinct products in that order; generated orders have at most
  four line items.
- The benchmark datasets are synthetic. They are deterministic and expose the
  algorithmic issue clearly, but a production decision should also be checked
  on representative real exports.

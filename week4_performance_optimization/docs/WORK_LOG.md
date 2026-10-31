# Work Log — Week 4 Performance Optimization

This is a phase/output record. It intentionally avoids invented calendar
timestamps: completion is established by the files and transcripts produced in
each phase.

| Phase | Work performed | Verifiable output |
|---:|---|---|
| 1 | Designed the SalesLens workload: product/customer joins, multiple aggregations, duplicates, repeat customers and co-purchases | Canonical result contract implemented in both engines |
| 2 | Built a seeded synthetic-data generator with popularity skew, multi-line orders, duplicate IDs and invalid rows | `saleslens/data_generator.py`; deterministic generator tests |
| 3 | Implemented the original baseline using list searches/buckets and multiple passes | `saleslens/baseline.py` |
| 4 | Built correctness tests from a hand-calculated fixture before relying on differential parity | 8-row oracle in `tests/conftest.py` and `test_correctness.py` |
| 5 | Profiled the baseline and identified master-search, grouping, duplicate and bucket costs | `results/profiles/baseline_cprofile.txt` |
| 6 | Implemented the optimized engine with dictionary indexes, hash aggregation and streaming | `saleslens/optimized.py` |
| 7 | Built an interleaved benchmark that refuses to time until exact result equality passes | `benchmark.py`; JSON/CSV/Markdown results |
| 8 | Measured 2,000/5,000/10,000 rows plus an optimized-only 100,000-row check | 19.16×/40.05×/79.87× paired speedups; 100k in 0.8014 s |
| 9 | Profiled the optimized engine and ran isolated `timeit` experiments | 13,833,156 → 322,723 function calls; microbenchmark files |
| 10 | Generated charts, terminal figures, raw transcripts and project metrics from real executions | 9 figures under `docs/evidence/figures/` |
| 11 | Added user/engineering documentation, evidence index and submission description | README, performance analysis, evidence index, this log |
| 12 | Packaged and fresh-extraction verified the self-contained project | ZIP verification recorded at submission preparation |

## Problems encountered and resolutions

### 1. The first scaling target was too expensive for the baseline

An early 10,000-row smoke test already took several seconds, implying that a
30,000-row paired benchmark with repeats and profiling would waste substantial
time without adding much interpretive value. The paired study was capped at
10,000 rows, where the scaling trend is unambiguous, and a separate
optimized-only 100,000-row run demonstrates practical scalability.

### 2. Profiler time could have produced a misleading speedup

cProfile expands call-heavy baseline code from about 6.2 s unprofiled to
10.229 s profiled. The report therefore uses cProfile only for hotspot/call
analysis and uses unprofiled, interleaved median timings for speed claims.

### 3. Timing a wrong answer would be meaningless

Differential equality was made a hard benchmark gate. In addition, parity
alone was not treated as proof of correctness: a small hand-computed dataset
checks both engines against independently derived values.

### 4. Top-N tie ordering initially risked silent behaviour change

Sorting by revenue alone leaves equal-revenue products/customers in
implementation-dependent order. Both engines use metric descending and ID
ascending; optimized `heapq.nlargest` uses `_DescendingString` to express the
reverse string component exactly, with a dedicated tie test.

### 5. Memory measurement could contaminate time measurement

`tracemalloc` runs were separated from wall/CPU timing runs. This means memory
figures are comparable as Python-allocation peaks without adding tracing
overhead to headline seconds.

### 6. Evidence rendering needed correction

The first pytest figure duplicated a short transcript because the selected
head and tail overlapped. Machine-specific absolute paths also made cProfile
figures wrap badly. The rendering function now selects the whole short test
output once and shortens path prefixes only in rendered figures, leaving raw
profiles untouched.

### 7. Index memory was a real trade-off, not an automatic win

Dictionary customer/order sets could have increased memory. Separate
`tracemalloc` runs showed the opposite on this workload because the optimized
engine no longer retains raw and enriched dictionaries for every transaction.
The report records this as a measured outcome, not an assumption.

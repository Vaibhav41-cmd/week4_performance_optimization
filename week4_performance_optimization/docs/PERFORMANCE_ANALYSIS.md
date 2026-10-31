# Performance Analysis — SalesLens (Week 4)

## 1. Executive summary

SalesLens analyzes retail CSV exports containing product/customer master data
and transaction line items. The original implementation is functionally
correct but repeatedly performs linear searches inside the transaction loop.
Profile-guided optimization replaced those searches with hash indexes and a
single streaming pass while preserving the public API and canonical outputs.

At the largest paired benchmark scale (10,000 transaction rows), median
end-to-end time improved from **6.1780 s to 0.0774 s**, a **79.87× speedup**
and **98.7% time saving**. Peak traced memory fell from **15.76 MiB to
5.83 MiB**. Results were exactly equal before timing, and all 17 automated
tests pass.

## 2. Application and workload

### 2.1 Inputs

- `products.csv`: 500 products with category and unit price.
- `customers.csv`: 3,000 customers with region.
- `transactions.csv`: variable-size order line items.

The benchmark uses 2,000, 5,000 and 10,000 transaction rows generated with
seed 42. The product/customer master sizes remain fixed to isolate transaction
scaling. At 10,000 rows the canonical result contains 9,990 valid rows, 10
invalid rows, 5,617 orders, 2,383 customers and net revenue INR
102,073,944.29.

### 2.2 Outputs

Both engines calculate global revenue, monthly/category/region revenue,
top products/customers, repeat/high-value customers, duplicate transaction
IDs, co-purchase pairs and best month. This mix is deliberate: it includes
lookups, grouping, distinct counting, aggregation, sorting/selection and
order-level set operations rather than a single arithmetic loop.

### 2.3 Canonical-output contract

The optimized implementation was required to preserve:

- validation and invalid-row semantics;
- first-record-wins behaviour for duplicate master IDs;
- monetary rounding to two decimals;
- category-share/repeat-rate rounding to four decimals;
- key order in result dictionaries;
- top-N ordering: metric descending, ID ascending;
- formatted report text.

## 3. Measurement methodology

### 3.1 Benchmark harness

`benchmark.py`:

1. generates or reuses a deterministic dataset;
2. runs both engines and asserts exact result-dictionary equality;
3. performs interleaved timed repeats (baseline ×3, optimized ×5);
4. records wall time with `time.perf_counter` and CPU time with
   `time.process_time`;
5. reports min/median/mean/standard deviation;
6. measures `tracemalloc` current/peak allocations in separate runs;
7. writes JSON, CSV and Markdown summaries.

Median values are used for headline comparisons. A conservative speedup
(slowest optimized run versus fastest baseline run) is also retained in JSON.

### 3.2 Profiling

`tools/run_profiling.py` runs cProfile at 10,000 rows and stores both
`tottime` and cumulative views. It also runs best-of-five `timeit`
microbenchmarks for the isolated data-structure operations. cProfile totals
are not used as benchmark timings because instrumentation inflates call-heavy
code disproportionately.

### 3.3 Environment

- CPython 3.13.16
- Linux 6.1.158+ x86_64, glibc 2.41
- 2 CPUs reported by `os.cpu_count()`
- Python executable `/usr/local/bin/python3`

Only same-machine paired comparisons are interpreted.

## 4. Baseline architecture and expected bottlenecks

The baseline (`saleslens/baseline.py`) is a plausible first implementation:

- `_find_by_id` scans the product and customer lists for each transaction;
- `_add_to_bucket` scans a list of bucket dictionaries for each of five
  aggregation families;
- `_distinct_add` implements a set with a list;
- `_count_duplicate_ids` calls `ids.count(value)` for every ID;
- customer order counting and co-purchase grouping search nested lists;
- all enriched rows are retained and scanned in successive passes.

Let `n` be transaction rows, `p`/`c` master-record counts, `o` distinct
orders and `k` distinct products/customers. The expensive terms are
approximately `O(n(p+c))` for joins, `O(nk)` for buckets/distinct operations,
`O(n·o)` for list-backed order grouping and `O(n²)` for duplicate counting.
The generated data makes these terms grow rapidly even though each function
looks innocuous in isolation.

## 5. Baseline cProfile evidence

At 10,000 rows, the profiled baseline made **13,833,156 function calls** in
10.229 profiled seconds. The highest internal-time functions were:

| Function/operation | Calls | `tottime` | `cumtime` | Diagnosis |
|---|---:|---:|---:|---|
| `_find_by_id` | 19,988 | 2.461 s | 4.536 s | Repeated master scans dominate |
| `_co_purchase_pairs` | 1 | 2.203 s | 2.224 s | Order groups and pair records are list-searched |
| `dict.get` | 13,172,264 | 2.105 s | 2.105 s | Millions of probes from search loops |
| `list.count` | 9,990 | 1.324 s | 1.324 s | Duplicate detection rescans all IDs each time |
| `_distinct_add` | 40,002 | 0.556 s | 0.563 s | Lists used for set membership |
| `_customer_order_counts` | 1 | 0.511 s | 0.517 s | Nested customer/order lists |
| `_add_to_bucket` | 49,950 | 0.501 s | 0.502 s | Five bucket searches per valid row |
| `_strptime` internals | 10,000 | 0.107 s | 0.201 s | Secondary parsing overhead |

The first seven internal-time entries total about 9.66 s of `tottime`, but
overlapping cumulative values must not be summed. The optimization therefore
focused on algorithmic/data-structure changes rather than micro-tuning the CSV
reader or report formatter.

## 6. Optimized design

### 6.1 Master indexes

`_load_products` and `_load_customers` build ID-indexed dictionaries once.
Product price conversion also happens once. Existing duplicate master IDs are
ignored after the first record to preserve baseline semantics.

### 6.2 Single streaming transaction pass

`analyze_dataset` streams `csv.DictReader` rows and updates all aggregates in
one loop:

- scalar totals;
- monthly/category/region dictionaries;
- product `[revenue, units]` accumulators;
- customer revenue and distinct-order sets;
- transaction-ID `Counter`;
- order-to-product sets.

### 6.3 Hash-based grouping and counting

Sets replace distinct lists; `Counter` replaces repeated `list.count`;
`defaultdict(set)` replaces list-backed order groups; customer distinct
orders are sets keyed by customer.

### 6.4 Lower-overhead validation and selection

The optimized engine binds hot methods locally, validates timestamps with
`datetime.fromisoformat`, slices the month prefix, and uses
`heapq.nlargest` for top-10 selection. A small `_DescendingString` wrapper
allows a heap key to express “metric descending, ID ascending” exactly.

### 6.5 Complexity after optimization

After `O(p+c)` indexing, the transaction loop is expected `O(n)` for hash
operations, plus the sum over orders of `s_i choose 2` for co-purchase pairs
(where `s_i` is the distinct-product count in an order). Top-N selection is
`O(k log 10)`. Memory is proportional to master data, distinct aggregates,
customer-order memberships and retained order-product sets—not to a full list
of enriched row dictionaries.

## 7. Results

### 7.1 End-to-end wall time

| Rows | Baseline runs (s) | Optimized runs (s) | Median baseline | Median optimized | Median speedup | Conservative speedup |
|---:|---|---|---:|---:|---:|---:|
| 2,000 | 0.4028, 0.4045, 0.4101 | 0.0210, 0.0211, 0.0229, 0.0211, 0.0238 | 0.4045 | 0.0211 | 19.16× | 16.94× |
| 5,000 | 1.7185, 1.7614, 1.7251 | 0.0412, 0.0406, 0.0431, 0.0463, 0.0437 | 1.7251 | 0.0431 | 40.05× | 37.14× |
| 10,000 | 6.0860, 6.3125, 6.1780 | 0.0823, 0.0811, 0.0739, 0.0761, 0.0774 | 6.1780 | 0.0774 | 79.87× | 73.98× |

The standard deviations are small relative to medians (at 10,000 rows:
baseline 0.1139 s, optimized 0.0035 s), and CPU medians track wall medians,
confirming a CPU-bound difference rather than an I/O scheduling artefact.

### 7.2 Scaling interpretation

When rows increase 5× from 2,000 to 10,000:

- baseline median grows about 15.3× (superlinear), consistent with nested
  list scans;
- optimized median grows about 3.7×, closer to linear after fixed master-load
  and runtime overheads.

The speedup therefore increases with scale, as expected when an
`O(n·k)`/`O(n²)` design is replaced with expected linear processing.

### 7.3 Memory

| Rows | Baseline peak | Optimized peak | Change |
|---:|---:|---:|---:|
| 2,000 | 4.31 MiB | 1.91 MiB | −55.7% |
| 5,000 | 8.68 MiB | 3.46 MiB | −60.1% |
| 10,000 | 15.76 MiB | 5.83 MiB | −63.0% |

Although dictionaries and sets are not free, avoiding raw plus enriched copies
of every transaction more than compensates on the tested workloads.

### 7.4 Optimized-only 100,000-row check

The baseline was not forced through a long quadratic 100,000-row run. The
optimized engine processed 99,900 valid rows and 56,199 orders in **0.8014 s**,
with **39.36 MiB** peak traced memory. This is evidence of practical
scalability, not a paired speedup claim.

### 7.5 Optimized profile

The optimized cProfile at 10,000 rows records 322,723 calls. Its largest
entries are the single `analyze_dataset` loop (0.072 s `tottime`), CSV
iteration (0.030 s), dictionary `get` (110,958 calls, 0.023 s), `next` and set
`add`. The remaining work is proportional input processing rather than hidden
nested scans. The 97.7% call reduction is an explanatory metric, not a direct
speedup measurement.

### 7.6 Microbenchmarks

| Isolated operation | Baseline choice | Optimized choice | Best-of-5 speedup |
|---|---:|---:|---:|
| Lookup near end of 3,000 records | 118.280 µs/op | 0.032 µs/op | 3,643.5× |
| Membership in 5,000 IDs | 50.239 µs/op | 0.023 µs/op | 2,165.5× |
| Aggregate 5,000 values/500 buckets | 43,220 µs/batch | 455 µs/batch | 94.9× |
| Parse timestamp/derive month | 5.922 µs/op | 0.230 µs/op | 25.8× |

The first two are deliberately near-end/worst-position list searches, so they
explain mechanism rather than predict application speedup. The authoritative
result remains the end-to-end benchmark.

## 8. Correctness verification

The testing strategy combines independent expectations with differential
(parity) testing:

1. A hand-calculated 8-row dataset has net revenue 680.0, Category A/B revenue
   430.0/250.0, four orders and one co-purchase pair; both engines must match
   the full expected dictionary.
2. Empty data, repeated product within an order, top-N ties and duplicate
   master records are tested for each engine.
3. Generated datasets with 0, 25, 250 and 1,000 rows are checked for exact
   baseline/optimized result and formatted-report equality.
4. Generator determinism and invalid dimensions are tested.
5. The benchmark itself refuses to time a dataset until exact parity passes.

Latest full run: **17 passed in 0.15 s**.

## 9. Trade-offs and threats to validity

- **Synthetic workload:** the generator exposes the relevant scaling patterns,
  but real exports may have different cardinality/skew.
- **CSV surface:** parity is guaranteed and tested for the supported generated
  export schema. The optimized `csv.DictReader` is in fact more capable with
  quoted fields than the baseline's manual comma split; such inputs can be a
  behavioural superset rather than byte-for-byte legacy behaviour.
- **Hash worst cases:** dictionary/set operations are expected O(1), not a
  cryptographic worst-case guarantee.
- **Memory model:** `tracemalloc` measures Python allocations, not total RSS
  or allocator arenas retained by the process.
- **Large orders:** co-purchase output itself can be quadratic in distinct
  products per order; no index can remove the cost of enumerating all pairs.
- **Fixed master sizes:** benchmark scales transactions with fixed 500/3,000
  master files. Scaling all dimensions together is a useful future experiment.
- **Single implementation language/runtime:** results are CPython-specific;
  pandas/NumPy, PyPy, multiprocessing or C extensions were outside this
  standard-library optimization scope.

## 10. Optimization log

| Profile evidence | Change | Main effect |
|---|---|---|
| `_find_by_id` 4.536 s cumulative | Product/customer dict indexes, prices parsed once | Removes per-row master scans and millions of probes |
| `_co_purchase_pairs` 2.224 s cumulative | `defaultdict(set)`, `Counter`, `combinations` | Hash grouping replaces list-of-group searches |
| `list.count` 1.324 s | Transaction-ID `Counter` in main pass | Removes repeated full-list scans |
| `_distinct_add`/customer counts | Sets and customer→order-set dict | Distinct operations become expected O(1) |
| `_add_to_bucket` 49,950 calls | Dict/defaultdict accumulators | Aggregation no longer searches buckets |
| Retained all raw/enriched rows | Streaming aggregates | Fewer passes, allocations and calls; lower traced peak |
| Date parse entries | `fromisoformat` + prefix slice | Lower constant-factor parsing cost |
| Repeated max/remove top-N | `heapq.nlargest` with exact tie key | Clean bounded selection |

## 11. Reproduction checklist

```bash
python -m pytest -v
python benchmark.py --sizes 2000,5000,10000 \
  --baseline-repeats 3 --optimized-repeats 5 \
  --optimized-only-size 100000 --force-generate
python tools/run_profiling.py --rows 10000
python run.py --engine baseline --data-dir data/sample
python run.py --engine optimized --data-dir data/sample
```

Expected: 17 tests pass; both sample runs produce the same analytics; the
benchmark prints `Parity: PASS` before each timing block.

# SalesLens benchmark summary

Generated: 2026-10-31T16:42:59.592381+00:00
Python: 3.13.16

| Rows | Baseline median | Optimized median | Speedup | Time saved | Baseline peak | Optimized peak |
|---:|---:|---:|---:|---:|---:|---:|
| 2,000 | 0.4045 s | 0.0211 s | 19.16x | 94.8% | 4.31 MiB | 1.91 MiB |
| 5,000 | 1.7251 s | 0.0431 s | 40.05x | 97.5% | 8.68 MiB | 3.46 MiB |
| 10,000 | 6.1780 s | 0.0774 s | 79.87x | 98.7% | 15.76 MiB | 5.83 MiB |

Optimized-only scalability check: 100,000 rows in 0.8014 s; peak traced memory 39.36 MiB.

Parity was checked by exact equality of the canonical result dictionaries before timing.
Memory is peak Python allocation measured by `tracemalloc` in separate runs.

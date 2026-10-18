# Reproducible demonstration

Run `python examples/demo.py` from `Code` after installing `requirements.txt`. The script creates a temporary SQLite database and reads the four bundled sample PDFs.

## Successful four-supplier run

| Rank | Supplier | Absolute score / 100 | PPI / 100 |
| ---: | --- | ---: | ---: |
| 1 | NexaWorks | 84.00 | 90.00 |
| 2 | Apex Systems | 77.00 | 83.11 |
| 3 | Orbit Digital | 66.00 | 70.78 |
| 4 | BrightPath Tech | 62.00 | 66.67 |

`examples/example_run.json` contains the full run, including criterion evidence, peer benchmarks, gaps, warning lists and the tie-break rule.

## Validation case

The demonstration sends one criterion score of `99` for a maximum of `10` and omits the other four criteria. Validation clips the first score to `10`, inserts zero for each missing criterion and records warnings. The resulting score vector is `[10, 0, 0, 0, 0]`. This case exercises normalization without making an API call.

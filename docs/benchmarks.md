# Benchmarks

## FinOps cross-vendor suite (BO002)

Proof that VOLY saves money on the **executor billing-fallback chain** (Layer B),
not by widening the model-gateway provider list (Layer A).

| Path | Role |
|---|---|
| [benchmarks/finops-suite/REPORT.md](../benchmarks/finops-suite/REPORT.md) | GTM one-pager (stable narrative) |
| [benchmarks/finops-suite/README.md](../benchmarks/finops-suite/README.md) | How to run mock/live |
| `benchmarks/finops-suite/run.py --mode mock` | Regenerates `results/results.{json,md}` |

```bash
python benchmarks/finops-suite/run.py --mode mock
pytest tests/test_finops_benchmark_suite.py -q
```

Headline from the checked-in narrative: **~26% saved** vs single-vendor top-up baseline on the mock suite; mid-chain quota task uses four executors (`claude-code` → `zen`).

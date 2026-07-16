# FinOps suite — cross-vendor proof (BO002)

Reproducible task set for **Layer B** savings: executor chain + billing fallback,
not model-gateway provider width (Layer A).

Plan (cloud repo): `voly-cloud/docs/plans/bo002-cross-vendor-finops-benchmark.md`  
**GTM one-pager:** [REPORT.md](./REPORT.md)

## Layout

| Path | Role |
|---|---|
| `tasks.yaml` | 8 fixed tasks + mock cost / fallback specs |
| `fixture_project/` | Tiny cwd with intentional defects (copied per run) |
| `suite.py` | Load + validate |
| `harness.py` | Phase 2: baseline vs VOLY via real `AgentRunner` |
| `run.py` | `--mode mock` (CI) / `--mode live` (gated) |
| `REPORT.md` | Phase 3 — external-safe GTM narrative |
| `results/` | Generated — **gitignored** (`results.json`, `results.md`) |

## Run (Phase 2)

```bash
# from open-core repo root
python benchmarks/finops-suite/run.py --mode mock
pytest tests/test_finops_benchmark_suite.py -q
```

Outputs:

- `results/results.json` — rows + summary (`baseline_usd`, `voly_usd`, `saved_*`)
- `results/results.md` — markdown table for GTM draft

### Arms

| Arm | Meaning |
|---|---|
| **baseline** | Primary-only `claude-code`. On `billing_fallback` tasks: failed attempt + top-up success (single-vendor finish). |
| **VOLY** | Full `BILLING_FALLBACK_CHAIN` with TaskEvent retry-aware totals |

Costs come from `TaskEvent` / `chain_timelog` semantics — not a parallel spreadsheet.

## Live mode (opt-in)

```bash
python benchmarks/finops-suite/run.py --mode live --confirm
```

Requires `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`. Live AgentRunner arms are
not wired yet (aborts before spend). Do not enable in CI.

## Anti-scope

- No new AIGateway providers
- Not a LiteLLM / OpenRouter comparison
- Do not commit `results/` or `.voly/events/`

## Claims

| Claim | How |
|---|---|
| C1 billing fallback | `billing_fallback` rows → positive `saved_usd` |
| C2 retry-aware cost | AgentRunner TaskEvent totals |
| C3 ≥2 vendors | `executors_used` length ≥ 2 on fallback rows |
| C4 vs baseline | `saved_pct` in results table |

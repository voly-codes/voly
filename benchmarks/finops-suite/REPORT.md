# VOLY FinOps — cross-vendor proof (one-pager)

**Suite:** `finops-cross-vendor-v1`  
**Mode:** deterministic mock (CI-reproducible)  
**Layer:** B — orchestration over file-capable CLI agents  
**Not:** another model gateway / LiteLLM / OpenRouter

Reproduce:

```bash
python benchmarks/finops-suite/run.py --mode mock
# → results/results.json + results/results.md
```

---

## The problem

One coding-agent vendor = one credit ceiling. When Claude Code (or any paid CLI) hits quota, the task stops — or the team tops up the same vendor and pays again at the same rate. FinOps controls that live *inside* a single vendor’s product do not help when the work must continue on another executor.

---

## What VOLY proves

VOLY’s billing fallback chain walks **file-capable executors across vendors**, keeps a retry-aware `$` total on every task, and finishes the work when the primary CLI is exhausted:

```text
claude-code → wrangler → opencode → zen
```

This is **Layer B** (orchestration + cost telemetry), not Layer A (more LLM providers).

| Claim | Evidence in suite |
|---|---|
| **C1** Fallback lowers finish cost when paid CLI quota is exhausted | 4 `billing_fallback` tasks → positive `saved_usd` |
| **C2** Full cost with retries, no double-count | Totals from `TaskEvent` / `AgentRunner` (same semantics as production) |
| **C3** Cross-vendor (≥2 executor labels) | e.g. `claude-code, wrangler, opencode, zen` |
| **C4** Measurable vs single-vendor baseline | Suite **saved 26.3%** overall in mock run |

---

## Headline numbers (mock run)

| | USD |
|---|---:|
| Baseline (primary-only / top-up fiction) | **$0.137** |
| VOLY (full fallback chain) | **$0.101** |
| **Saved** | **$0.036 (26.3%)** |

On billing-fallback tasks only, all savings concentrate there (`billing_fallback_saved = $0.036`). Happy-path tasks (no quota stress) show `$0` delta — same primary executor, as expected.

### Mid-chain quota (spotlight)

Task `midchain-quota`: forced exhaustion across the chain until `zen`.

| Arm | USD | Executors used |
|---|---:|---|
| Baseline (fail + top-up on `claude-code`) | 0.040 | `claude-code` only |
| VOLY | 0.029 | `claude-code` → `wrangler` → `opencode` → `zen` |
| **Saved** | **0.011 (27.5%)** | **4 vendors in one task** |

Same pattern as the integration path in `tests/test_failure_paths.py`, with dollars attached for GTM — not only asserts.

---

## Full suite table

| task_id | baseline_usd | voly_usd | saved_usd | saved_pct | executors_used | fallback |
|---|---:|---:|---:|---:|---|---|
| tiny-rename | 0.0240 | 0.0190 | 0.0050 | 20.8% | claude-code, wrangler, opencode, zen | yes |
| add-docstring | 0.0080 | 0.0080 | 0.0000 | 0.0% | claude-code | no |
| fix-off-by-one | 0.0300 | 0.0150 | 0.0150 | 50.0% | claude-code, wrangler, opencode, zen | yes |
| noop-review | 0.0050 | 0.0050 | 0.0000 | 0.0% | claude-code | no |
| add-type-hint | 0.0060 | 0.0060 | 0.0000 | 0.0% | claude-code | no |
| fix-greet-typo | 0.0200 | 0.0150 | 0.0050 | 25.0% | claude-code, wrangler, opencode | yes |
| counter-docstring | 0.0040 | 0.0040 | 0.0000 | 0.0% | claude-code | no |
| midchain-quota | 0.0400 | 0.0290 | 0.0110 | 27.5% | claude-code, wrangler, opencode, zen | yes |

---

## How to read the baseline

- **Happy path:** baseline = one successful `claude-code` run (same as VOLY → `$0` saved).
- **Billing fallback:** baseline = failed primary attempt **plus** a top-up success still on `claude-code` (what a single-vendor team pays to finish). VOLY instead walks cheaper/free executors and records the full chain cost.

Mock costs are fixtures in `tasks.yaml` for reproducibility. Live CLI arms are opt-in and separate; do not treat mock `$` as production invoices.

---

## What this is *not*

- **Not** “we support more model providers than OmniRoute / LiteLLM / OpenRouter.”
- **Not** a latency or token-price bake-off between gateways.
- **Not** a reason to expand Layer A. VOLY deliberately **delegates** model routing and competes on **executor orchestration + FinOps**.

Pitch line for Team tier: *the same measurable `$` that saves a solo run becomes org spend history when the agent is linked to VOLY Cloud.*

---

## Reproduce & verify

```bash
python benchmarks/finops-suite/run.py --mode mock
pytest tests/test_finops_benchmark_suite.py -q
```

| Artifact | Role |
|---|---|
| `benchmarks/finops-suite/tasks.yaml` | Fixed task + mock cost specs |
| `results/results.json` | Machine-readable rows + summary |
| `results/results.md` | Regenerated table (may refresh timestamps) |
| This `REPORT.md` | Stable GTM narrative (update when suite claims change) |

---

*Apache-2.0 open-core. Hosted Team control plane is separate (`voly-cloud`).*

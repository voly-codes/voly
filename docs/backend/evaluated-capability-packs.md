# Evaluated agent and skill packs

Phase 8 adds measured capability packs above the existing executor registry.
They do not replace native VOLY routing: an inactive, retired, unmeasured, or
unmatchable pack returns an explicit native fallback.

## Pilot packs

| Capability | Role | Dimension | Typical triggers |
|---|---|---|---|
| `security-reviewer.v1` | security | security | secrets, auth, threat, vulnerabilities |
| `tdd-workflow.v1` | tester | testing | TDD, test-first, regressions, failing tests |
| `python-reviewer.v1` | reviewer | backend | Python, pytest, Ruff, typing, pyproject |

Every pack declares `CapabilityInput.v1`, `CapabilityOutput.v1`, trigger scope,
and numerical success criteria. Inputs carry task, role, project features,
changed files and acceptance criteria. Outputs carry completion, findings,
tests, recommendations and evidence IDs.

## Routing

```text
task → role → active measured capability → ExecutorMatcher → executor → model
```

Only packs with `state=active` and `evidence_count>0` participate. Executor and
model selection remains owned by the existing matcher. No match, degraded
matching, disabled evaluated routing, or no relevant pack produces
`native_fallback=true`.

## Evidence, activation, and retirement

Each paired baseline/variant record tracks completion, test pass, rollback,
corrections, cost, latency, retries, reviewer acceptance, quality delta and a
held-out marker for one capability/executor pair. Experiments declaring more
than one changed capability are rejected.

Activation requires measured evidence, including for imported capabilities.
Retirement waits for the minimum sample count, then removes packs with no
measurable added value or failed completion/testing/rollback/correction/review
criteria from evaluated routing.

```yaml
capability:
  evaluated_enabled: false
  evaluated_dir: .voly/capability/evaluated
```

```bash
voly capability evaluated init
voly capability evaluated record outcome.json
voly capability evaluated metrics security-reviewer claude-code
voly capability evaluated activate security-reviewer
voly capability evaluated route "review auth security" --role security
voly capability evaluated evaluate-retirement security-reviewer claude-code
```

Experiment state remains ignored under `.voly/capability/`.

The production gate and bundled 20-task suite are documented in
[production-validation.md](production-validation.md). An offline routing probe
cannot activate a capability; activation requires real paired outcomes and
held-out evidence.

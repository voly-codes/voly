# Deterministic Eval Engine

`voly/evaluation/` is the first Phase 2 increment of Evidence-Based Agent
Governance. It defines success before execution, repeats trusted deterministic
checks after execution, and attaches the complete result to EvidenceRecord v2.
It is record-only: evaluation does not yet block the visible executor result or
drive primary routing.

## Execution flow

For a file-capable `AgentRunner` run with both `evidence.enabled` and
`evaluation.enabled`:

```text
task classification
→ select versioned EvalPolicy
→ repository baseline (exact argv retained)
→ executor / fallback / safety
→ file-change evidence
→ replay baseline commands with shell=false
→ EvalReport
→ root-cause attribution
→ EvidenceRecord v2
```

Policy selection occurs before execution. Evaluation runs after safety rollback,
so it checks the files that will actually remain in the repository.

## Built-in policies

| Task type | Policy |
|---|---|
| `docs`, `documentation` | `documentation-basic@1` |
| `tests`, `testing` | `testing-basic@1` |
| other / unknown | `executor-basic@1` |

Each v1 policy requires:

1. executor success;
2. no hard safety-policy violation;
3. at least one retained file change;
4. successful replay of every baseline command that passed before execution.

The separate policy ids intentionally establish versioned lineages even though
their first deterministic requirement sets are currently identical.

## Final states

| State | Meaning |
|---|---|
| `verified_success` | every required deterministic evaluator passed |
| `partial_success` | execution succeeded, but required verification was unavailable or skipped |
| `soft_failure` | execution succeeded but a required post-run evaluator failed |
| root-cause state | executor failed; EvidenceRecord retains `hard_failure`, `environment_failure`, or `policy_violation` from root-cause attribution |

`EvidenceOutcome.success` continues to describe executor success during the
record-only rollout. `EvidenceOutcome.state` and `evaluation.state` carry the
stronger verified state.

## Exact command replay

BaselineCheck v2 retains both:

- `command`: display-only text;
- `argv`: the exact argument vector executed with `shell=False`.

Eval Engine reuses `argv` directly and never reparses display text. Legacy
records without `argv` fail closed to `partial_success` instead of risking a
false verification. Command timeouts are bounded by
`evaluation.command_timeout_seconds`.

Only exit code `0` passes. In particular, pytest exit codes for test failures,
interrupts, internal errors, usage errors, no tests collected, or excessive
warnings remain failures.

## Privacy

The complete local EvalReport may contain command arguments and bounded output
tails. Evidence Cloud schema v2 exports only:

- eval schema/policy versions;
- final state;
- evaluator id/type/status/required flag/duration.

Commands, output, messages and arbitrary detail never cross the Cloud
Analytics allowlist.

## Configuration

```yaml
evaluation:
  enabled: false
  policy_id: auto
  command_timeout_seconds: 120
```

Environment override: `VOLY_EVALUATION_ENABLED=1|0`.

The generated config is disabled for staged rollout. The checked-in dogfood
config enables record-only evaluation.

## Tests

```bash
python -m pytest tests/test_evaluation.py -q
python -m pytest tests/test_evidence_foundation.py tests/test_plan_verify.py -q
```

LLM judges, visual evaluation, human-review gates, golden datasets,
capability-score updates, decay and evidence-driven routing remain later Phase
2/3 work.

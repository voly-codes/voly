# Eval Engine

`voly/evaluation/` is the first Phase 2 increment of Evidence-Based Agent
Governance. It defines success before execution, repeats trusted deterministic
checks after execution, can run an explicitly enabled rubric-based LLM judge,
and attaches the complete result to EvidenceRecord v2. It is record-only:
evaluation does not yet block the visible executor result or drive primary
routing.

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

When `llm_judge.mode` is `shadow` or `required`, the selected policy version is
extended with `-judge-shadow.1` or `-judge-required.1`. This keeps deterministic,
shadow-judge and required-judge evidence in separate version lineages.

## Built-in policies

| Task type | Policy |
|---|---|
| `docs`, `documentation` | `documentation-basic@3` |
| `tests`, `testing` | `testing-basic@3` |
| `security` | `security-basic@2` |
| other / unknown | `executor-basic@2` |

Every policy requires:

1. executor success;
2. no hard safety-policy violation;
3. a policy-clean bounded execution trajectory;
4. at least one retained file change;
5. successful replay of every baseline command that passed before execution.

`documentation-basic@3` additionally requires:

6. valid local destinations in changed `.md` / `.mdx` files;
7. explicit human review.

`testing-basic@3` additionally requires at least one changed test artifact.
Recognized artifacts include pytest's standard `test_*.py` and `*_test.py`,
common JavaScript/TypeScript `.test.*` and `.spec.*` files, conventional test,
fixture and snapshot directories, and common pytest/Jest/Vitest configuration
files. This structural check complements baseline replay: it proves that a
testing task retained a test-related change, while replay proves that the
pre-existing deterministic command still passes.

`security-basic@2` additionally requires:

6. a diff-scoped static scan of changed supported source files;
7. explicit human review.

The security scan reuses VOLY's bounded risk patterns for hardcoded secrets,
formatted SQL execution, `eval`, subprocess shell execution and unsafe YAML
loading. It records only the finding label, repository-relative path and
generic description; matched code and possible secret values are never stored
in EvalReport. Unsupported or oversized changes make the scan `skipped` and
the run `partial_success`. An unreadable or outside-repository source path
fails closed. Pre-existing findings in unchanged files do not poison a
diff-based run.

## Trajectory policy

The v1 trajectory evaluator consumes only standardized local runner metadata.
It aggregates executor attempts, fallback status counts, inner retry count,
dry-run state, rollback count and whether a tool trace is available. Billing
or availability fallback is evidence, not an automatic failure. Any safety
event, rollback, or malformed trajectory metadata fails the requirement.

The evaluator never copies fallback error text, safety paths or tool arguments
into its detail. Not every executor currently exposes a standardized tool-call
trace, so `tool_trace_available: false` is recorded explicitly. File access,
retained changes and bounded side effects remain covered by the separate
file-change and safety evaluators; full cross-executor tool/permission tracing
remains future work.

## Rubric-based LLM judge

The optional judge uses one explicit, versioned rubric selected by task type:

| Task type | Rubric |
|---|---|
| documentation | `documentation@1` |
| testing | `testing@1` |
| security | `security@1` |
| other | `general-code@1` |

Every rubric has separately weighted dimensions. Correctness and other
task-specific safety dimensions are critical: a critical score below `2/4`
cannot pass even when the weighted score exceeds the configured threshold.
The model must return a strict JSON object with exactly:

```json
{
  "verdict": "pass",
  "dimensions": [
    {"id": "correctness", "score": 4, "reason": "bounded reason"}
  ],
  "summary": "bounded summary"
}
```

The parser requires every rubric dimension exactly once, scores in `0..4`,
bounded strings, and no extra keys or Markdown fences. VOLY computes the
weighted result itself; it does not trust the model's `pass` label alone.
`uncertain`, gateway failure, invalid JSON, and schema violations become
`skipped`, preventing false verification. A valid rubric failure becomes
`failed`.

The system prompt treats task and executor output as untrusted quoted data to
reduce prompt-injection risk. The judge receives no repository source and no
file paths, only bounded task text plus bounded executor output. This still
sends potentially sensitive text to the configured model provider, so the
feature is `off` by default and must be enabled explicitly.

This first judge is a report-level evaluator: it judges the bounded executor
output, not the repository diff. Deterministic tests, safety, trajectory,
artifact and human checks remain the stronger evidence for actual code state.

### Rollout and calibration

- `off`: no judge requirement and no model call;
- `shadow`: run the judge as optional evidence; its result cannot change the
  final EvalReport state;
- `required`: make the judge a required check; a valid judge failure produces
  `soft_failure`, while unavailable or invalid judge evidence produces
  `partial_success`.

Explicit human feedback adds a calibration event to a completed judge check:
human label, judge label, agreement flag and feedback kind. It never rewrites
the original judge score. This per-run signal is the input for later aggregate
calibration and drift monitoring; an LLM judge remains only one evidence source
and is never the sole high-risk security approval.

Judge tokens and estimated cost are included in the run totals. Cached judge
responses add zero cost. When the provider omits token counts, VOLY records
bounded estimates with `tokens_estimated: true`.

The Markdown evaluator checks inline destinations and reference definitions,
ignores fenced examples plus external/anchor/site-root URLs, percent-decodes
relative paths, resolves symlinks and rejects destinations outside the
repository. It validates file existence, not heading anchors. CommonMark
destinations with deeply nested parentheses are outside the v1 evaluator
subset.

Human review begins as `pending`, so an otherwise clean documentation or
security run is `partial_success`. Explicit `accepted` feedback passes the requirement. The
signals `edited`, `major_rewrite`, `reverted`, `pr_rejected`, and `manual_fix`
fail it and produce `soft_failure`. Later feedback revises the same review
check, preserving the append-only feedback history.

## Final states

| State | Meaning |
|---|---|
| `verified_success` | every required evaluator passed |
| `partial_success` | execution succeeded, but required verification was unavailable, skipped, or pending |
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
  llm_judge:
    mode: off
    model: ""
    provider: ""
    max_input_chars: 6000
    max_tokens: 1200
    threshold: 0.75
```

Environment overrides:

- `VOLY_EVALUATION_ENABLED=1|0`;
- `VOLY_LLM_JUDGE_MODE=off|shadow|required`.

The generated config is disabled for staged rollout. The checked-in dogfood
config enables record-only evaluation.

## Tests

```bash
python -m pytest tests/test_evaluation.py -q
python -m pytest tests/test_evidence_foundation.py tests/test_plan_verify.py -q
```

Visual evaluation, approval blocking, golden datasets, capability-score
updates, decay and evidence-driven routing remain later Phase 2/3 work.

## Design references

- [OWASP Secure Code Review Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secure_Code_Review_Cheat_Sheet.html)
  motivates diff-based review and combining automated findings with human
  judgment.
- [pytest good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
  defines the standard Python test discovery names used by the testing
  evaluator.
- [OpenAI Graders](https://platform.openai.com/docs/api-reference/graders)
  documents explicit model graders, score ranges, structured outputs and
  multi-dimensional grading.

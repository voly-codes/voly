# Task tags and cost per trusted outcome

Tracking issue: [voly-codes/voly#9](https://github.com/voly-codes/voly/issues/9)

Status: planned. None of the task-tagging acceptance criteria are implemented
yet. `TaskEvent` is schema v4 and the Spend Protocol remains v1.

## Goal

Make spend reviews useful at repository and project level, then connect that
spend to an observed outcome:

- what changed;
- what was deterministically verified;
- what remained partial or failed;
- what was abandoned and retried;
- how much the complete outcome cost.

The first release supports both sources of task identity:

1. inferred tags from the effective executor workspace;
2. explicit repeatable tags supplied by the operator.

Inference supplies a safe default for ordinary runs. Explicit tags add team,
initiative or cost-centre context and may override an inferred key with the
same namespace. Tags are normalized as `key:value`, deduplicated and stored in
deterministic order.

## Existing foundation

- `TaskEvent.cost_usd`, `retry_cost_usd` and `chain_timelog` preserve total and
  abandoned-attempt spend.
- `WorkReport` records files created, changed and deleted.
- `EvidenceRecord v2` joins execution identity, `EvidenceOutcome.cost_usd`,
  files changed and the evaluation state.
- Eval Engine states distinguish `verified_success`, `partial_success` and
  `soft_failure`.

These records are not yet queryable as a single FinOps report and currently
carry no repository/project tags.

## Implementation checklist

### Identity and schema

- [ ] Define canonical `repo`, `project`, `team`, `initiative` and custom tag
  semantics, normalization, maximum counts and size limits.
- [ ] Derive `repo:<identity>` and `project:<name>` from the effective `--cwd`
  and project configuration without exposing private absolute paths.
- [ ] Add repeatable `voly run --tag key:value`; retain `--label` as an alias
  only if it does not make the CLI contract ambiguous.
- [ ] Define precedence when an explicit tag uses the same namespace as an
  inferred tag.
- [ ] Add tags to a new version of `TaskEvent`; update the local serializer,
  Cloud Analytics allowlist, API documentation and frozen contract tests.
- [ ] Version the Spend Protocol before adding tags to `/spend/record`.
- [ ] Keep unknown tags backward-compatible for older local event files.

### Reporting

- [ ] Add task/event filtering by exact tag.
- [ ] Add grouping by repository, project and arbitrary tag.
- [ ] Aggregate cost, input/output tokens, retry cost, tasks and files touched.
- [ ] Join local task telemetry with `EvidenceOutcome.state` by `task_id`.
- [ ] Report cost per trusted outcome without treating executor self-report as
  verification.
- [ ] Keep `verified_success`, partial, failed and abandoned spend separate.
- [ ] Add deterministic JSON and CSV exports for weekly reviews.

### UI

- [ ] Show repository/project tags in task history and the cost view.
- [ ] Add multi-select tag filters with a clear empty state.
- [ ] Display totals for the active filter.
- [ ] Add outcome-state grouping and a cost-per-verified-outcome metric.
- [ ] Never display raw inferred absolute workspace paths.

### Verification

- [ ] Add schema migration and backward-compatibility tests.
- [ ] Cover explicit tags, inferred tags, precedence and normalization.
- [ ] Cover CLI, API, Spend Protocol and Cloud Analytics privacy boundaries.
- [ ] Verify filtering and grouping totals against mixed tagged/legacy events.
- [ ] Verify retry/abandoned spend is included exactly once.
- [ ] Verify only evidence-backed `verified_success` counts as trusted.
- [ ] Add UI tests for filtering, totals and outcome grouping.
- [ ] Document a reproducible local smoke run using two repositories.

## Acceptance criteria

- `voly run "fix" --cwd <repo> --tag team:backend` persists normalized inferred
  repository/project tags plus the explicit team tag.
- A report filtered by `repo:<identity>` contains only matching tasks and
  reconciles cost, tokens, retry spend and files touched.
- UI totals match CLI JSON totals for the same filter.
- Cost-per-trusted-outcome divides spend only by evidence-backed verified
  outcomes and exposes partial, failed and abandoned spend separately.
- No private absolute workspace path enters Cloud Analytics or exported
  receipts by default.

## Non-goals

- Organization-wide tag policy and billing governance.
- Treating an LLM judge as the sole proof of a trusted outcome.
- Uploading raw prompts, source paths, repository contents or evidence details.

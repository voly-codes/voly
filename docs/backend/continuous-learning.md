# Instincts and continuous learning

Phase 6 introduces an opt-in, local learning store. It does not inject learned
text into prompts. Selection is shadow-only, so policy, security, routing, and
tool permissions remain authoritative.

## Atomic instinct

An instinct contains one trigger and one action plus:

- scope and scope ID (`project`, `organization`, or `global`);
- confidence from 0 to 1;
- append-only evidence with source and project provenance;
- contradiction source IDs;
- lifecycle: `candidate`, `approved`, `suspended`, or `retired`.

Candidates start at confidence `0.25`. Mere observations, including a completed
`TaskEvent`, do not increase it. Verified tests, accepted reviews, explicit user
acceptance, or another verified outcome add `0.15`. Rollback, contradiction,
user correction, failed tests, and retries subtract `0.20`. Rollback,
contradiction, and correction also suspend an approved instinct.

Manual `voly learning approve` is the only approval path. It requires at least
one positive evidence item. There is deliberately no active prompt-injection
mode in this phase.

## Evidence sources

`InstinctStore` accepts:

- `TaskEvent` outcomes and retries;
- `EvidenceRecord` evaluation and human feedback;
- business Decision approval/rejection and downstream execution outcomes;
- explicit test, review, rollback, retry, contradiction, and user-correction
  signals through `voly learning evidence`.

Use `voly learning ingest-evidence` to classify an existing EvidenceRecord.
Human feedback such as `reverted`, `major_rewrite`, `manual_fix`, or
`pr_rejected` becomes a `user_correction` penalty. Accepted feedback and passed
evaluation are positive evidence.

When learning is enabled, `DecisionService` records an approved business
option as `user_accepted`, a rejection as `user_correction`, and successful
execution as `verified_outcome`. These events update a candidate's evidence
and confidence only. They never approve or activate an instinct; manual
`voly learning approve` remains mandatory.

## Workflow

```bash
voly learning propose "pytest failure" "run the focused test first" \
  --project-id project-a --evidence-kind test_passed --source-id test-123
voly learning approve <instinct-id>
voly learning shadow "pytest failure in API" --project-id project-a
voly learning evidence <instinct-id> rollback rollback-7 --project-id project-a
voly learning remove <instinct-id>
```

Global promotion requires manual approval and positive evidence from at least
two project IDs. Stable, approved, contradiction-free instincts can be grouped
into versioned skill candidates with `voly learning skill-candidates`. These
are metadata candidates only; they are not installed or activated.

Actions containing explicit policy/security bypass instructions are rejected
at ingestion. Learned content has no mechanism to override system instructions,
permissions, scanners, or policy gates.

```yaml
learning:
  enabled: false
  mode: shadow
  store_path: .voly/learning/instincts.json
  min_skill_confidence: 0.7
```

The learning store is runtime state under ignored `.voly/learning/`.

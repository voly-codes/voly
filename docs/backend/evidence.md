# Evidence Foundation

`voly/evidence/` is the first implementation phase of Evidence-Based Agent
Governance. It records deterministic facts around file-capable executor runs;
it does not yet make primary routing decisions.

## Execution order

For `AgentRunner.run()` with `evidence.enabled: true`:

```text
start RunRecord heartbeat
→ capture repository baseline
→ optional DSPy task refinement
→ git/safety snapshot
→ executor + billing fallback
→ WorkReport
→ root-cause classification
→ atomic EvidenceRecord write
→ TaskEvent
→ Capability Registry evidence hook
```

The baseline is captured before the executor can edit files. Baseline commands
may create ignored caches or build artifacts, so the later git/safety snapshot
is intentionally taken after baseline capture.

## EvidenceRecord v1

Records are JSON files under `evidence.store_dir` (default
`.voly/evidence/<task_id>.json`) and contain:

- task type and a SHA-256 task fingerprint, never the raw task prompt;
- repository stack, package managers, test frameworks and baseline checks;
- agent, executor, exact reported model/provider, VOLY runtime version;
- skill version/commit slots and eval-policy id/version;
- cost, duration, retry count, files changed and executor outcome;
- root-cause class plus `penalize_agent`;
- human feedback as a separate list from automated evidence.

`schema_version` is currently `1`. Change the schema version when removing a
field or changing field semantics. Additive readers should continue tolerating
older records when migrations are introduced.

## Repository baseline

`capture_repository_baseline()` scans the target `cwd` with `ProjectScanner`.
When `baseline_auto_commands` is enabled, it discovers conservative commands:

| Project signal | Baseline command |
|---|---|
| `package.json` with `scripts.build` | package-manager `run build` |
| `go.mod` | `go build ./...` |
| `Cargo.toml` | `cargo check` |
| `pom.xml` | `mvn package -DskipTests -q` |
| detected test stack | command from `voly.plan.suggest` |
| explicitly detected ruff/eslint/golangci-lint | matching lint command |

Commands run with `subprocess.run`, an argv list, `shell=False`, the target
`cwd`, captured output and a bounded timeout. A configured
`baseline_commands` entry overrides an auto-discovered command with the same
name.

Baseline health values:

| Health | Meaning |
|---|---|
| `healthy` | all executed checks passed |
| `metadata_only` | repository scanned but no commands were available |
| `preexisting_failure` | a command ran and returned non-zero |
| `environment_failure` | cwd/scan/executable/timeout/OS failure |

Baseline is best-effort infrastructure. An exception is logged and must not
prevent the requested executor from running.

## Root-cause classification

Initial deterministic mapping:

| Signal | Failure class | Penalize agent |
|---|---|---|
| billing | `provider_failure` | no |
| executor unavailable | `tool_failure` | no |
| timeout | `tool_failure` | no |
| safety rejection | `policy_violation` | no |
| unhealthy environment baseline | `environment_failure` | no |
| pre-existing failing baseline | `repository_failure` | no |
| otherwise failed executor | `agent_failure` | yes |

Capability Registry v1 now skips negative EMA updates when
`penalize_agent=false`. Successful executor outcomes retain the existing v1
scoring until the Eval Engine can provide verified-success evidence.

## Human feedback hook

`EvidenceStore.add_human_feedback()` atomically appends one of:

```text
accepted
edited
major_rewrite
reverted
pr_rejected
manual_fix
```

Feedback can be recorded through either local interface:

```bash
voly evidence show <task_id>
voly evidence feedback <task_id> accepted --comment "merged unchanged"
```

```http
GET  /api/evidence/{task_id}
POST /api/evidence/{task_id}/feedback
Content-Type: application/json

{"kind": "edited", "comment": "renamed helper before merge"}
```

The CLI records `source=cli`; the API records `source=api`. Clients cannot
override this provenance field. Comments are optional, local-only, and limited
to 2,000 characters. Task ids accept only 1-128 ASCII letters, digits,
underscores and hyphens, starting with a letter or digit. This prevents an
interface-supplied id from escaping `evidence.store_dir`.

The store serializes feedback read-modify-write operations inside one VOLY
process and retains atomic replacement for readers. There is intentionally no
automatic capability-score update from human feedback yet; calibrated weights
belong to a later Evidence Foundation increment.

## Remote privacy boundary

Local EvidenceRecord files are never suitable for direct upload: baseline
commands, output excerpts, notes and human comments can contain repository or
customer data. `evidence_to_cloud_record()` constructs a new object from a
strict allowlist:

- pseudonymous SHA-256 evidence id rather than the local task id;
- task type, baseline health and detected stack metadata;
- check name/status/timing/failure kind, without command or output;
- executor/model/runtime/eval-policy versions;
- structured outcome metrics;
- human feedback kind/source, without comment or exact feedback timestamp.

It excludes `task_fingerprint`, repository observations, file paths and
free-form text. The sanitizer does not upload by itself; every remote
destination is additionally gated by `cloud_analytics.enabled=false` by
default. The remote allowlist has its own `schema_version: 1` and records the
local EvidenceRecord version as `source_schema_version`. This keeps consent,
data minimization and schema evolution independent and fail-closed.

## Storage and safety

`EvidenceStore.save()` writes a temporary file in the destination directory,
flushes and fsyncs it, then calls `os.replace()` so readers never observe a
partially written record. `.voly/evidence/` is generated local state and must
not be committed or uploaded as Cloud analytics. The local HTTP API exposes
complete records, including comments, and is therefore for localhost use only.

## Configuration

```yaml
evidence:
  enabled: false
  store_dir: ".voly/evidence"
  baseline_enabled: true
  baseline_auto_commands: true
  baseline_commands: {}
  baseline_timeout_seconds: 120
  output_max_chars: 2000
  eval_policy_id: executor-basic
  eval_policy_version: "1"
```

Environment override: `VOLY_EVIDENCE_ENABLED=1|0`.

The checked-in dogfood `voly.yaml` enables evidence. The generated default
configuration keeps it disabled for staged rollout until a team has reviewed
the commands inferred for its repositories.

## Tests

```bash
python -m pytest tests/test_evidence_foundation.py -q
python -m pytest tests/test_capability_evidence.py -q
```

`TaskEvent v3` is unchanged; EvidenceRecord is a separate local contract.

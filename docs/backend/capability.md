# Capability Registry

> Added: Phase 3. Source: `voly/capability/`

## Purpose

Evidence-based executor routing. Each executor has a measured capability
profile; routing score replaces static tier resolution.

## Two profile kinds

- **executor**: for developer/tester/devops roles → `AgentRunner.run(executor=X)`
- **model_provider**: for architect/reviewer/security roles → `AIGateway.chat(model=X)`

## Routing score formula

```
capability_match × 0.40 + historical_success × 0.20 + tool_compatibility × 0.15
+ project_stack_match × 0.10 + availability × 0.05 + cost_efficiency × 0.05 + latency × 0.05
```

## Modules

| Module | Role |
|--------|------|
| `schema.py` | Dataclasses: `ExecutorCapabilityProfile`, `CapabilityDomain`, `CapabilityMatchResult` |
| `calibration.py` | Benchmark → VOLY dimension mapping (`calibrate()`) |
| `registry.py` | Load/save profiles from `.voly/capability/profiles/` YAML cache |
| `scorer.py` | Pure routing score + hard-gate functions (`routing_score()`, `hard_exclude()`) |
| `matcher.py` | `ExecutorMatcher` — CF Worker `/match` with local fallback |
| `seeds/` | Bundled seed profiles for known executors |

## Matcher + Scorer

### `ExecutorMatcher.find_executors()` workflow

1. If a worker URL is configured (`ExecutorMatcher(worker_url=…)` or `MatchRequest.worker_url`), POST to `{worker_url}/match` with `dimension` and optional `available_executors`.
2. On success, assemble a `CapabilityMatchResult` from the JSON response (`recommended`, `fallbacks`, `excluded`), loading full profiles from the local registry.
3. On any HTTP error, timeout, or unreachable worker, fall through to **local fallback**: load all known profiles, apply `hard_exclude()`, score with `routing_score()`, sort descending, return top-1 as recommended plus the rest as fallbacks. Sets `degraded=True` when no executor passes the gates.

### `routing_score()` weights

| Component | Weight | Source |
|-----------|--------|--------|
| `capability_match` | 0.40 | `profile.capabilities[dimension].score` (0.5 if unknown) |
| `historical_success` | 0.20 | `successful_runs / max(1, internal_runs)` |
| `tool_compatibility` | 0.15 | 1.0 if `file_tools`, else 0.0 |
| `project_stack_match` | 0.10 | 0.5 neutral if no features; else matching-feature fraction |
| `availability` | 0.05 | 1.0 (Phase 5 will add live checks) |
| `cost_efficiency` | 0.05 | `max(0, 1 - cost_per_task_usd)`; 1.0 if free |
| `latency` | 0.05 | `max(0, 1 - avg_latency_ms / 120000)` |

### `hard_exclude()` gate conditions

| Condition | Exclusion reason |
|-----------|------------------|
| `requires_file_tools=True` and `constraints.file_tools=False` | `missing_file_tools` |
| `requires_browser_tools=True` and `constraints.browser_tools=False` | `missing_browser_tools` |

Returns `None` when the profile passes all active gates.

### `MatchRequest` fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dimension` | `str` | — | Capability dimension (e.g. `backend`, `frontend`) |
| `available_executors` | `list[str] \| None` | — | Restrict to these IDs; `None` = all known |
| `project_features` | `list[str] \| None` | — | Detected stack features for stack-match scoring |
| `requires_file_tools` | `bool` | `True` | Hard-gate: executor must support file tools |
| `requires_browser_tools` | `bool` | `False` | Hard-gate: executor must support browser tools |
| `worker_url` | `str` | `""` | Override CF Worker base URL for this request |
| `worker_timeout_s` | `float` | `5.0` | Remote match HTTP timeout |

## Profile lifecycle

```
seed (voly/capability/seeds/) → materialized copy (.voly/capability/profiles/) → EMA updates from runs
```

On first `load()`, a seed profile is copied into `.voly/capability/profiles/`. Subsequent reads use the materialized copy. `reset` removes the materialized file so the seed is re-applied on next load.

## CLI

```bash
voly capability list
voly capability show claude-code
voly capability match "implement REST API" --dimension backend --features python fastapi
voly capability match "build UI" --dimension frontend --features react --executors claude-code cursor
voly capability reset claude-code
voly capability reset --all
```

## Cloud schema

D1 tables for remote sync: `cf-workers/capability/schema.sql` (`roles`, `executor_capability`, `executor_constraints`, `executor_operational`).

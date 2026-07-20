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
| `seeds/` | Bundled seed profiles for known executors |

## Profile lifecycle

```
seed (voly/capability/seeds/) → materialized copy (.voly/capability/profiles/) → EMA updates from runs
```

On first `load()`, a seed profile is copied into `.voly/capability/profiles/`. Subsequent reads use the materialized copy. `reset` removes the materialized file so the seed is re-applied on next load.

## CLI

```bash
voly capability list
voly capability show claude-code
voly capability reset claude-code
voly capability reset --all
```

## Cloud schema

D1 tables for remote sync: `cf-workers/capability/schema.sql` (`roles`, `executor_capability`, `executor_constraints`, `executor_operational`).

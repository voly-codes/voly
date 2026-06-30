# Catalog & Supervisor

> **Status:** implemented locally; optional Cloudflare Worker support is available.

CodeOps **Catalog** stores model metadata and routing hints. The **Supervisor** layer uses that catalog to plan executor/model/skill combinations for multi-step work.

This component is now generic and project-agnostic. Product-specific combat missions should live outside the CodeOps core repository.

---

## Why it exists

| Problem | Catalog/Supervisor role |
|---|---|
| Models change often | Sync model metadata instead of hardcoding everything in prompts |
| Different tasks need different runtimes | Route implementation to file-capable executors, review to readonly models |
| Cost varies per provider/model | Prefer cheaper/free models for suitable tasks |
| Multi-step work needs planning | Produce a structured plan before execution |
| Teams need repeatable policies | Keep routing rules and model metadata reusable |

---

## Architecture

```text
codeops catalog sync
        │
        ▼
OpenCode Zen API / fallback catalog
        │
        ▼
.codeops/catalog/models.json
        │
        ▼
Catalog routing
        │
        ├─ codeops catalog list
        ├─ codeops catalog match <task>
        └─ Supervisor plan helpers
                │
                ▼
Executor/model/skill plan
```

Optional remote catalog:

```text
CodeOps CLI → CatalogClient → CF Worker → D1/R2/Vectorize/KV
```

---

## Python modules

| Module | Path | Purpose |
|---|---|---|
| Types | `codeops/catalog/types.py` | `CatalogModel`, plan/spec dataclasses |
| Zen sync | `codeops/catalog/zen_sync.py` | fetch/parse OpenCode Zen model metadata |
| Store | `codeops/catalog/store.py` | local cache under `.codeops/catalog/` |
| Routing | `codeops/catalog/routing.py` | task matching and model/executor selection |
| Supervisor | `codeops/catalog/supervisor.py` | planning helpers for multi-step execution |
| CF client | `codeops/catalog/client.py` | optional remote worker client |
| Multi-agent | `codeops/executor/multi_agent.py` | sequential/parallel executor tasks |

---

## CLI

```bash
# Sync model metadata
codeops catalog sync

# Sync and push to CF Worker when configured
codeops catalog sync --push

# List catalog entries
codeops catalog list
codeops catalog list --tier free
codeops catalog list --json

# Match an ad-hoc task
codeops catalog match "review migration plan for database risks"

# Create a routing plan if supported by current rules
codeops catalog plan <plan-id>
```

---

## OpenCode Zen and GO

| Gateway | Typical executor | Endpoint | File changes |
|---|---|---|---|
| OpenCode GO | `opencode` | `OPENCODE_BASE_URL` | yes, when used through file-capable flow |
| OpenCode Zen | `zen` | `OPENCODE_ZEN_BASE_URL` | no, text-only analysis/review |

Environment:

| Variable | Required | Purpose |
|---|---:|---|
| `OPENCODE_API_KEY` | for OpenCode | Zen + GO auth |
| `OPENCODE_ZEN_BASE_URL` | no | default Zen endpoint |
| `OPENCODE_BASE_URL` | no | default GO endpoint |
| `CF_WORKER_CATALOG_URL` | optional | remote catalog worker |

---

## Planning model

A supervisor plan should be explicit and auditable:

```yaml
steps:
  - id: audit
    agent: reviewer
    executor: zen
    model: deepseek-v4-flash-free
    readonly: true
    skills:
      - design-critique
    task: |
      Review the proposed migration and list risks.

  - id: implementation
    agent: developer
    executor: cursor
    model: composer
    readonly: false
    skills:
      - component-patterns
    task: |
      Implement the approved migration in the target project.
```

Supervisor should not silently rewrite business requirements. It may enrich the execution spec with:

- executor;
- model;
- readonly flag;
- skill ids;
- cost/free-tier preference;
- fallback hints.

---

## Skills injection

Skill content may be injected into system prompts where the executor/runtime supports it.

Recommended lookup order:

1. target project skill directory, if configured;
2. local `.codeops/skills/`;
3. repository `.claude/skills/`, if present;
4. remote marketplace/catalog, if configured.

Readonly tasks should receive an explicit instruction:

```text
READONLY MODE: Do NOT edit or create files. Review and report only.
```

---

## Telemetry

Each planned/executed step should be represented as `TaskEvent` where possible.

| Field | Source |
|---|---|
| `agent` | selected agent role |
| `executor` | cursor / opencode / zen / etc. |
| `model` | selected model |
| `skill_ids` | skills injected into the step |
| `workflow` | plan id / workflow id |
| `cost_usd` | executor result or `_estimate_cost()` |
| `automation_score` | `compute_automation_metrics()` |

Useful commands:

```bash
codeops savings
codeops spend summary
codeops telemetry status
```

---

## Deploy CF Catalog Worker

```bash
cd cf-workers/catalog
npm install
npx wrangler d1 execute codeops --file=schema.sql --remote
npx wrangler deploy
```

After deployment:

```bash
export CF_WORKER_CATALOG_URL="https://<worker-url>"
codeops catalog sync --push
```

---

## Notes

- Catalog is reusable infrastructure, not a product-specific mission system.
- Generated cache under `.codeops/catalog/` is runtime state.
- Product-specific plans should be kept in the downstream project repository.

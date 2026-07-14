# Catalog & Supervisor

> **Status:** implemented locally; optional Cloudflare Worker support is available.

VOLY **Catalog** stores model metadata and routing hints. The **Supervisor** layer uses that catalog to plan executor/model/skill combinations for multi-step work.

This component is now generic and project-agnostic. Product-specific combat missions should live outside the VOLY core repository.

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
voly catalog sync                voly catalog import-freellm SOURCE
        │                                   │
        ▼                                   ▼
OpenCode Zen API / fallback     awesome-freellm-apis README (offline)
        │                                   │
        └──────────────┬────────────────────┘
                       │  merge_with_catalog()
                       ▼
             .voly/catalog/models.json
                       │
                       ▼
               Catalog routing
                       │
                       ├─ voly catalog list
                       ├─ voly catalog match <task>
                       ├─ verified_free_fallback()  ← opt-in, not wired to gateway
                       └─ Supervisor plan helpers
                       │
                       ▼
            Executor/model/skill plan
```

See [catalog-freellm.md](catalog-freellm.md) for the freellm integration details.

Optional remote catalog:

```text
VOLY CLI → CatalogClient → CF Worker → D1/R2/Vectorize/KV
```

---

## Python modules

| Module | Path | Purpose |
|---|---|---|
| Types | `voly/catalog/types.py` | `CatalogModel` (v1 + v2 fields), plan/spec dataclasses |
| Zen sync | `voly/catalog/zen_sync.py` | fetch/parse OpenCode Zen model metadata |
| FreeLLM importer | `voly/catalog/freellm_importer.py` | offline README parser + merge |
| Fallback | `voly/catalog/fallback.py` | `verified_free_fallback()` pure function |
| Store | `voly/catalog/store.py` | local cache under `.voly/catalog/` |
| Routing | `voly/catalog/routing.py` | task matching and model/executor selection |
| Supervisor | `voly/catalog/supervisor.py` | planning helpers for multi-step execution |
| CF client | `voly/catalog/client.py` | optional remote worker client |
| Multi-agent | `voly/executor/multi_agent.py` | sequential/parallel executor tasks |

---

## CLI

```bash
# Sync model metadata from OpenCode Zen
voly catalog sync
voly catalog sync --push          # also push to CF Worker

# Import free LLM models from awesome-freellm-apis (no network required)
voly catalog import-freellm /path/to/awesome-freellm-apis/
voly catalog import-freellm /path/to/README.md --dry-run   # preview only
voly catalog import-freellm /path/to/README.md --json      # output JSON
voly catalog import-freellm /path/to/README.md --push      # local + remote

# List catalog entries
voly catalog list
voly catalog list --tier free
voly catalog list --json

# Match an ad-hoc task
voly catalog match "review migration plan for database risks"

# Create a routing plan if supported by current rules
voly catalog plan <plan-id>
```

---

## OpenCode Zen and GO

| Gateway | Typical executor | Endpoint | File changes |
|---|---|---|---|
| OpenCode GO | `opencode` | `OPENCODE_BASE_URL` | yes, file-capable |
| OpenCode Zen | `zen` | `OPENCODE_ZEN_BASE_URL` | **yes** — `zen` is file-capable and is the last executor in `BILLING_FALLBACK_CHAIN` (`claude-code → wrangler → zen`) |

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
2. local `.voly/skills/`;
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
voly savings
voly spend summary
voly telemetry status
```

---

## Deploy CF Catalog Worker

```bash
cd cf-workers/catalog
npm install
npx wrangler d1 execute voly --file=schema.sql --remote
npx wrangler deploy
```

After deployment:

```bash
export CF_WORKER_CATALOG_URL="https://<worker-url>"
voly catalog sync --push
```

---

## Notes

- Catalog is reusable infrastructure, not a product-specific mission system.
- Generated cache under `.voly/catalog/` is runtime state.
- Product-specific plans should be kept in the downstream project repository.

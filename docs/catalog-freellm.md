# FreeLLM Catalog Integration

> **Status:** implemented; offline-only (read-only external source, no vendoring)

VOLY can import free LLM provider metadata from the community-maintained
[awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-free-llm-apis)
repository (MIT license) and merge it into the local model catalog.

---

## Data origin and attribution

| Field | Value |
|---|---|
| Source | `awesome-freellm-apis` README (MIT © open-free-llm-api) |
| Sections parsed | `<!-- BEGIN_QUICK_REF -->`, `<!-- BEGIN_PERMANENT_FREE -->`, `<!-- BEGIN_BEST_MODELS -->` |
| Update frequency | README is refreshed daily upstream; VOLY imports on-demand, not automatically |
| VOLY relationship | **Read-only**: VOLY never writes to the external repository |
| Vendoring | **Prohibited**: do not copy or commit the external repository inside VOLY |

---

## Architecture

```text
awesome-freellm-apis/README.md   (external, read-only checkout)
            │
            ▼
  voly catalog import-freellm SOURCE
            │
            ├─ parse_readme(path) — offline Markdown parser
            │      ├─ Quick Reference → base_url, api_key_url, auth_requirement
            │      ├─ Permanent Free  → modalities
            │      └─ Best Free Models → model_id, context_window, rate_limit
            │
            ├─ merge_with_catalog(existing, imported)
            │      ├─ preserves all non-freellm models
            │      ├─ adds new freellm models (verified=False by default)
            │      └─ enriches existing entries with new metadata fields
            │
            └─ save_models(.voly/catalog/models.json)  ← local offline fallback
                        │
                        └─ [--push] CatalogClient → CF Worker D1 (optional)
```

---

## Python modules

| Module | Path | Purpose |
|---|---|---|
| Importer | `voly/catalog/freellm_importer.py` | Parse README, merge catalogs |
| Fallback | `voly/catalog/fallback.py` | `verified_free_fallback()` pure function |
| Types | `voly/catalog/types.py` | `CatalogModel` (extended with v2 fields) |

---

## CLI

```bash
# Parse README and write to local catalog (no network)
voly catalog import-freellm /path/to/awesome-freellm-apis/README.md

# Or pass the checkout root directory
voly catalog import-freellm /path/to/awesome-freellm-apis/

# Dry-run: show parsed models without writing
voly catalog import-freellm SOURCE --dry-run

# Emit parsed models as JSON (implies no write)
voly catalog import-freellm SOURCE --json

# Write locally AND push merged catalog to remote CF Worker
voly catalog import-freellm SOURCE --push
```

### Without --push, no network calls are made.

---

## CatalogModel v2 fields

New optional fields added to `CatalogModel` (all backward-compatible; old JSON
without these fields loads safely with defaults):

| Field | Type | Default | Description |
|---|---|---|---|
| `base_url` | `str` | `""` | OpenAI-compatible base URL for the provider |
| `context_window` | `int` | `0` | Max context in tokens; 0 = unknown |
| `modalities` | `list[str]` | `[]` | e.g. `["audio", "text", "vision"]` |
| `rate_limit` | `dict` | `{}` | Structured: `rpm`, `rpd`, `tpm`, `tpd` keys (int) or `raw` (str) |
| `auth_requirement` | `str` | `""` | `none` / `email` / `phone` / `credit_card` |
| `api_key_url` | `str` | `""` | Direct link to the provider's key management page |
| `supports_tools` | `bool\|None` | `None` | `None` = unknown — never treat as True |
| `source_url` | `str` | `""` | Canonical URL of the model's info page |
| `upstream_model_id` | `str` | `""` | Provider-specific model ID sent to its API; catalog IDs are `<provider>:<upstream_model_id>` |
| `source_updated_at` | `str` | `""` | ISO date from the README's last-updated badge |
| `verified` | `bool` | `False` | Explicitly set by operator; never auto-set from source |
| `last_verified_at` | `str` | `""` | ISO date when `verified` was last set |

---

## verified flag and fallback selection

All models imported from the freellm README start with **`verified=False`**.

To use a model in `verified_free_fallback()`:

```python
from voly.catalog.fallback import verified_free_fallback
from voly.catalog.store import load_models

# Only returns enabled + tier=free + verified=True models
model = verified_free_fallback(load_models())

# Constrain to a specific executor
model = verified_free_fallback(load_models(), executor="zen")

# Require tool-calling support (supports_tools must be explicitly True)
model = verified_free_fallback(load_models(), require_tools=True)
```

To mark a model as verified after manual testing:

```python
from voly.catalog.store import load_models, save_models

models = load_models()
for m in models:
    if m.id == "google-gemini:gemini-3.5-flash":
        m.verified = True
        m.last_verified_at = "2026-07-14"
        # Compatibility is not present in the upstream source and must also be
        # confirmed explicitly before executor-constrained selection.
        m.executor_compat = ["zen"]
save_models(models)
```

### Accuracy limitations

Free tier availability, rate limits, and context windows change frequently.
The freellm README is refreshed daily, but VOLY imports only on-demand.
Treat imported data as **advisory, not authoritative** until verified.

- `supports_tools` is not documented in the README — always `None` for freellm imports.
- Rate limits for some providers are reported as `raw` strings (e.g., "Community-powered, no hard limit").
- `verified=False` models are excluded from `verified_free_fallback()` by design.

---

## Merge behaviour

```
merge_with_catalog(existing, imported)
```

| Scenario | Result |
|---|---|
| Model ID in existing only | Preserved unchanged |
| Model ID in imported only | Added with all freellm metadata, `verified=False` |
| Qualified model ID in both | Routing fields from **existing** (`tier`, `executor_compat`, `strengths`, `enabled`); metadata from **imported** (`base_url`, `context_window`, `rate_limit`, etc.); `verified` always from **existing** |
| Legacy raw model ID + matching provider | Existing row is enriched in place, preserving its legacy ID |

Catalog IDs are provider-qualified because multiple providers can expose the
same upstream model. The unmodified provider model name is stored separately in
`upstream_model_id`. Imported entries use `executor_compat=[]` because the source
does not describe VOLY executor compatibility.

Idempotent: importing the same README twice produces the same model set.

---

## Remote push (CF Worker)

When `--push` is passed, the merged catalog is sent to the CF Catalog Worker
via `POST /models/sync`. The worker now stores a `metadata` JSON blob column
containing all v2 fields alongside the core v1 columns.

**Schema migration** (existing databases): apply the one-time migration before
deploying the updated worker. D1/SQLite does not make this `ALTER TABLE`
idempotent, so record it in deployment history and do not run it twice.

```bash
# Existing deployment: apply once, then deploy
cd cf-workers/catalog
npx wrangler d1 execute voly --file=migrate/001_add_metadata.sql --remote
npx wrangler deploy

# Fresh deployment: schema.sql already includes the metadata column
npx wrangler d1 execute voly --file=schema.sql --remote

# Set up and push
export CF_WORKER_CATALOG_URL="https://<worker-url>"
voly catalog import-freellm /path/to/awesome-freellm-apis/ --push
```

The `GET /models?verified=true` filter is supported to retrieve only
verified models from the remote worker.

---

## Opt-in constraint

`verified_free_fallback()` is **not wired into the global AIGateway routing**.
It must be called explicitly by the code path that needs it.
This avoids adding untested free-tier providers to the live billing fallback chain.

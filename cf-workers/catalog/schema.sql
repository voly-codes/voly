-- VOLY Catalog — agents & models (synced from OpenCode Zen + freellm import)
CREATE TABLE IF NOT EXISTS models (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  provider TEXT DEFAULT '',
  tier TEXT DEFAULT 'standard',
  input_cost_per_1m REAL DEFAULT 0,
  output_cost_per_1m REAL DEFAULT 0,
  executor_compat TEXT DEFAULT '["zen"]',
  strengths TEXT DEFAULT '[]',
  enabled INTEGER DEFAULT 1,
  updated_at INTEGER NOT NULL,
  -- v2 metadata: JSON blob holding extended fields (base_url, context_window,
  -- modalities, rate_limit, auth_requirement, api_key_url, supports_tools,
  -- source_url, upstream_model_id, source_updated_at, verified,
  -- last_verified_at).
  -- Stored as a single column to avoid schema churn on every new field.
  metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_models_tier ON models(tier);
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider);

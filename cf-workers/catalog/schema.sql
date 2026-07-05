-- VOLY Catalog — agents & models (synced from OpenCode Zen)
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
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_models_tier ON models(tier);
CREATE INDEX IF NOT EXISTS idx_models_provider ON models(provider);

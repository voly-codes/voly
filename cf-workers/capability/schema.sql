CREATE TABLE IF NOT EXISTS roles (
  id TEXT PRIMARY KEY,
  tier TEXT NOT NULL,
  mode TEXT NOT NULL,
  system_prompt TEXT NOT NULL,
  default_executor TEXT DEFAULT '',
  provider_offset INTEGER DEFAULT 0,
  inject_prior_context INTEGER DEFAULT 0,
  decomposer_signals TEXT DEFAULT '[]',
  capability_requirements TEXT DEFAULT '{}',
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS executor_capability (
  executor_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  dimension TEXT NOT NULL,
  sub_dimension TEXT DEFAULT '',
  score REAL DEFAULT 0.5,
  confidence REAL DEFAULT 0.0,
  internal_runs INTEGER DEFAULT 0,
  successful_runs INTEGER DEFAULT 0,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (executor_id, dimension, sub_dimension)
);

CREATE TABLE IF NOT EXISTS executor_constraints (
  executor_id TEXT NOT NULL,
  constraint_name TEXT NOT NULL,
  value TEXT NOT NULL,
  PRIMARY KEY (executor_id, constraint_name)
);

CREATE TABLE IF NOT EXISTS executor_operational (
  executor_id TEXT PRIMARY KEY,
  avg_latency_ms REAL DEFAULT 0,
  completion_rate REAL DEFAULT 1.0,
  retry_rate REAL DEFAULT 0,
  cost_per_task_usd REAL DEFAULT 0,
  total_runs INTEGER DEFAULT 0,
  updated_at INTEGER NOT NULL
);

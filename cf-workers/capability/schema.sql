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

CREATE TABLE IF NOT EXISTS evaluated_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  schema_version INTEGER NOT NULL,
  executor_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  payload_sha256 TEXT NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluated_pack_state (
  capability_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  executor_id TEXT NOT NULL,
  snapshot_id TEXT NOT NULL,
  state TEXT NOT NULL,
  definition_hash TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  decision_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY (capability_id, version, executor_id),
  FOREIGN KEY (snapshot_id) REFERENCES evaluated_snapshots(snapshot_id)
);

CREATE INDEX IF NOT EXISTS idx_evaluated_pack_snapshot
  ON evaluated_pack_state(snapshot_id);

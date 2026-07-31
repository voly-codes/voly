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

CREATE TABLE IF NOT EXISTS a2a_agents (
  name TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  card_json TEXT NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS a2a_tasks (
  id TEXT PRIMARY KEY,
  agent_name TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'submitted',
  result TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_state ON a2a_tasks(state);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_agent ON a2a_tasks(agent_name);
CREATE INDEX IF NOT EXISTS idx_a2a_tasks_updated ON a2a_tasks(updated_at DESC);

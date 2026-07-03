-- VOLY Marketplace — D1 schema (fresh install)
-- For existing installs run: wrangler d1 execute codeops --file=migrate/001_add_content.sql --remote

CREATE TABLE IF NOT EXISTS skills (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT DEFAULT '',
  content TEXT DEFAULT '',        -- full skill instructions (injected into agent context)
  version TEXT DEFAULT '1.0.0',
  author TEXT DEFAULT '',
  source TEXT DEFAULT 'marketplace',
  status TEXT DEFAULT 'active',
  tags TEXT DEFAULT '[]',
  capabilities TEXT DEFAULT '[]',
  required_tools TEXT DEFAULT '[]',
  compatible_agents TEXT DEFAULT '[]',
  compatible_languages TEXT DEFAULT '[]',
  compatible_frameworks TEXT DEFAULT '[]',
  downloads INTEGER DEFAULT 0,
  usage_count INTEGER DEFAULT 0,
  success_rate REAL DEFAULT 1.0,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_skills_status ON skills(status);
CREATE INDEX IF NOT EXISTS idx_skills_source ON skills(source);
CREATE INDEX IF NOT EXISTS idx_skills_updated ON skills(updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS skills_fts USING fts5(
  id UNINDEXED,
  name,
  description,
  tags,
  content='skills',
  content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS skills_fts_insert AFTER INSERT ON skills BEGIN
  INSERT INTO skills_fts(rowid, id, name, description, tags)
  VALUES (new.rowid, new.id, new.name, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS skills_fts_update AFTER UPDATE ON skills BEGIN
  INSERT INTO skills_fts(skills_fts, rowid, id, name, description, tags)
  VALUES ('delete', old.rowid, old.id, old.name, old.description, old.tags);
  INSERT INTO skills_fts(rowid, id, name, description, tags)
  VALUES (new.rowid, new.id, new.name, new.description, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS skills_fts_delete AFTER DELETE ON skills BEGIN
  INSERT INTO skills_fts(skills_fts, rowid, id, name, description, tags)
  VALUES ('delete', old.rowid, old.id, old.name, old.description, old.tags);
END;

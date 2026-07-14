-- One-time migration for catalog databases created before FreeLLM metadata.
-- Apply once before deploying the worker version that reads `metadata`.
ALTER TABLE models ADD COLUMN metadata TEXT DEFAULT '{}';

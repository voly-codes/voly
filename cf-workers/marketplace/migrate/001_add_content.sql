-- Migration 001: add content column to skills table
-- Applied to existing databases where schema.sql was used before this column was added.
-- For fresh installs, schema.sql already includes the column.
ALTER TABLE skills ADD COLUMN content TEXT DEFAULT '';

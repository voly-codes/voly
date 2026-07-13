-- Migration 002: add package-based skill fields
-- Run: wrangler d1 execute voly --file=migrate/002_skill_packages.sql --remote

ALTER TABLE skills ADD COLUMN repository TEXT DEFAULT '';
ALTER TABLE skills ADD COLUMN install_kind TEXT DEFAULT 'single';

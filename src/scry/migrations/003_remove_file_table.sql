-- Migration 003: scry-spec v1.0 compliance
--
-- Removes legacy scry__file table and related objects.
-- Recreates scry__doc with an expanded kind CHECK to include the
-- v1.0 baseline kinds: lesson, report, audit, research, code.
--
-- SQLite does not support ALTER COLUMN, so scry__doc is recreated
-- via the standard rename/create/copy/drop pattern.

-- ---------------------------------------------------------------
-- 1. Drop scry__file FTS triggers
-- ---------------------------------------------------------------
DROP TRIGGER IF EXISTS scry__file_ai;
DROP TRIGGER IF EXISTS scry__file_ad;
DROP TRIGGER IF EXISTS scry__file_au;

-- ---------------------------------------------------------------
-- 2. Drop scry__file FTS virtual table and index
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS scry__file_fts;
DROP INDEX IF EXISTS scry__file_path_idx;

-- ---------------------------------------------------------------
-- 3. Drop scry__file
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS scry__file;

-- ---------------------------------------------------------------
-- 4. Drop scry__doc FTS triggers (will be recreated after rename)
-- ---------------------------------------------------------------
DROP TRIGGER IF EXISTS scry__doc_ai;
DROP TRIGGER IF EXISTS scry__doc_ad;
DROP TRIGGER IF EXISTS scry__doc_au;

-- ---------------------------------------------------------------
-- 5. Drop scry__doc FTS virtual table (will be recreated)
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS scry__doc_fts;

-- ---------------------------------------------------------------
-- 6. Create scry__doc_v2 with expanded kind CHECK
-- ---------------------------------------------------------------
CREATE TABLE scry__doc_v2 (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT CHECK(kind IN (
    'design','pattern','spec','lesson','internal',
    'task','milestone',
    'report','audit','research',
    'code',
    'clarification'
  )),
  weight REAL,
  status TEXT CHECK(status IN ('draft','active','approved','stale','complete')),
  tags TEXT,
  rationale TEXT,
  applies TEXT,
  seeded_questions TEXT,
  ephemeral INTEGER DEFAULT 0,
  missing_since TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 7. Copy existing data (kind values already conform or map to internal)
-- ---------------------------------------------------------------
INSERT INTO scry__doc_v2
  SELECT
    id, current_path, summary,
    CASE
      WHEN kind IN (
        'design','pattern','spec','lesson','internal',
        'task','milestone','report','audit','research','code','clarification'
      ) THEN kind
      ELSE 'internal'
    END AS kind,
    weight, status, tags, rationale, applies, seeded_questions,
    ephemeral, missing_since, content_hash, created_at, updated_at
  FROM scry__doc;

-- ---------------------------------------------------------------
-- 8. Drop old scry__doc, rename v2
-- ---------------------------------------------------------------
DROP TABLE scry__doc;
ALTER TABLE scry__doc_v2 RENAME TO scry__doc;

-- ---------------------------------------------------------------
-- 9. Recreate scry__doc index
-- ---------------------------------------------------------------
CREATE INDEX IF NOT EXISTS scry__doc_path_idx ON scry__doc(current_path);

-- ---------------------------------------------------------------
-- 10. Recreate scry__doc FTS virtual table
-- ---------------------------------------------------------------
CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__doc', content_rowid='rowid'
);

-- Populate FTS from current data
INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  SELECT rowid, id, summary, tags, rationale, applies, seeded_questions FROM scry__doc;

-- ---------------------------------------------------------------
-- 11. Recreate scry__doc FTS triggers
-- ---------------------------------------------------------------
CREATE TRIGGER IF NOT EXISTS scry__doc_ai AFTER INSERT ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__doc_ad AFTER DELETE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__doc_au AFTER UPDATE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
  INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;

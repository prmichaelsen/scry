-- Migration 004: scry-spec v1.0 — @scry.bind support
--
-- 1. Creates scry__bind table (replaces scry__impl and scry__test).
-- 2. Drops scry__impl and scry__test.
-- 3. Recreates scry__doc without the strict kind/status CHECK constraints,
--    so unknown kind and status values are preserved as-is (FR8, FR9).
--
-- scry-spec v1.0 defines @scry.bind as the single binding marker, replacing
-- the legacy @scry.impl and @scry.test markers. scry__bind uses rowid as its
-- primary key since local_id is file-scoped and comma-expansion can produce
-- multiple rows from a single marker line.

-- ---------------------------------------------------------------
-- 1. Drop scry__impl and scry__test
-- ---------------------------------------------------------------
DROP TABLE IF EXISTS scry__impl;
DROP TABLE IF EXISTS scry__test;
DROP INDEX IF EXISTS scry__impl_path_idx;
DROP INDEX IF EXISTS scry__test_path_idx;

-- ---------------------------------------------------------------
-- 2. Create scry__bind
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__bind (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  local_id TEXT NOT NULL,
  ref TEXT NOT NULL,
  comment TEXT,
  file_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE (local_id, ref, file_path)
);

CREATE INDEX IF NOT EXISTS scry__bind_file_path_idx ON scry__bind(file_path);
CREATE INDEX IF NOT EXISTS scry__bind_local_id_idx ON scry__bind(local_id);
CREATE INDEX IF NOT EXISTS scry__bind_ref_idx ON scry__bind(ref);

-- FTS for scry__bind — FR2 requires comments to be searchable.
CREATE VIRTUAL TABLE IF NOT EXISTS scry__bind_fts USING fts5(
  local_id, ref, comment,
  content='scry__bind', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS scry__bind_ai AFTER INSERT ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(rowid, local_id, ref, comment)
  VALUES (new.rowid, new.local_id, new.ref, new.comment);
END;

CREATE TRIGGER IF NOT EXISTS scry__bind_ad AFTER DELETE ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(scry__bind_fts, rowid, local_id, ref, comment)
  VALUES ('delete', old.rowid, old.local_id, old.ref, old.comment);
END;

CREATE TRIGGER IF NOT EXISTS scry__bind_au AFTER UPDATE ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(scry__bind_fts, rowid, local_id, ref, comment)
  VALUES ('delete', old.rowid, old.local_id, old.ref, old.comment);
  INSERT INTO scry__bind_fts(rowid, local_id, ref, comment)
  VALUES (new.rowid, new.local_id, new.ref, new.comment);
END;

-- ---------------------------------------------------------------
-- 3. Recreate scry__doc without kind/status CHECK constraints
--    (FR8/FR9: preserve original values as-is, never coerce)
-- ---------------------------------------------------------------
DROP TRIGGER IF EXISTS scry__doc_ai;
DROP TRIGGER IF EXISTS scry__doc_ad;
DROP TRIGGER IF EXISTS scry__doc_au;
DROP TABLE IF EXISTS scry__doc_fts;

CREATE TABLE scry__doc_v4 (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT,
  weight REAL,
  status TEXT,
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

INSERT INTO scry__doc_v4
  SELECT id, current_path, summary, kind, weight, status, tags, rationale,
         applies, seeded_questions, ephemeral, missing_since, content_hash,
         created_at, updated_at
  FROM scry__doc;

DROP TABLE scry__doc;
ALTER TABLE scry__doc_v4 RENAME TO scry__doc;

CREATE INDEX IF NOT EXISTS scry__doc_path_idx ON scry__doc(current_path);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__doc', content_rowid='rowid'
);

INSERT INTO scry__doc_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  SELECT rowid, id, summary, tags, rationale, applies, seeded_questions FROM scry__doc;

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

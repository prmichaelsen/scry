-- Initial schema for scry marker-indexed cache.

CREATE TABLE IF NOT EXISTS scry__doc (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT CHECK(kind IN ('design','spec','task','milestone','clarification','pattern','internal')),
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

CREATE TABLE IF NOT EXISTS scry__file (
  id TEXT PRIMARY KEY,
  current_path TEXT,
  summary TEXT,
  kind TEXT,
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

CREATE TABLE IF NOT EXISTS scry__anchor (
  name TEXT PRIMARY KEY,
  description TEXT,
  seeded_questions TEXT,
  current_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scry__impl (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL,
  file_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scry__test (
  id TEXT PRIMARY KEY,
  ref TEXT NOT NULL,
  file_path TEXT,
  content_hash TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS doc_relationship (
  from_id TEXT,
  to_id TEXT,
  relationship TEXT CHECK(relationship IN ('depends_on')),
  PRIMARY KEY (from_id, to_id, relationship)
);

CREATE INDEX IF NOT EXISTS scry__doc_path_idx ON scry__doc(current_path);
CREATE INDEX IF NOT EXISTS scry__file_path_idx ON scry__file(current_path);
CREATE INDEX IF NOT EXISTS scry__anchor_path_idx ON scry__anchor(current_path);
CREATE INDEX IF NOT EXISTS scry__impl_path_idx ON scry__impl(file_path);
CREATE INDEX IF NOT EXISTS scry__test_path_idx ON scry__test(file_path);

-- FTS5 indexes (external content)
CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__doc', content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__file_fts USING fts5(
  id, summary, tags, rationale, applies, seeded_questions,
  content='scry__file', content_rowid='rowid'
);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__anchor_fts USING fts5(
  name, description, seeded_questions,
  content='scry__anchor', content_rowid='rowid'
);

-- Triggers to keep FTS in sync with source tables.
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

CREATE TRIGGER IF NOT EXISTS scry__file_ai AFTER INSERT ON scry__file BEGIN
  INSERT INTO scry__file_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__file_ad AFTER DELETE ON scry__file BEGIN
  INSERT INTO scry__file_fts(scry__file_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__file_au AFTER UPDATE ON scry__file BEGIN
  INSERT INTO scry__file_fts(scry__file_fts, rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES ('delete', old.rowid, old.id, old.summary, old.tags, old.rationale, old.applies, old.seeded_questions);
  INSERT INTO scry__file_fts(rowid, id, summary, tags, rationale, applies, seeded_questions)
  VALUES (new.rowid, new.id, new.summary, new.tags, new.rationale, new.applies, new.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__anchor_ai AFTER INSERT ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(rowid, name, description, seeded_questions)
  VALUES (new.rowid, new.name, new.description, new.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__anchor_ad AFTER DELETE ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(scry__anchor_fts, rowid, name, description, seeded_questions)
  VALUES ('delete', old.rowid, old.name, old.description, old.seeded_questions);
END;

CREATE TRIGGER IF NOT EXISTS scry__anchor_au AFTER UPDATE ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(scry__anchor_fts, rowid, name, description, seeded_questions)
  VALUES ('delete', old.rowid, old.name, old.description, old.seeded_questions);
  INSERT INTO scry__anchor_fts(rowid, name, description, seeded_questions)
  VALUES (new.rowid, new.name, new.description, new.seeded_questions);
END;

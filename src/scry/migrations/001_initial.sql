-- scry-mcp initial schema (v0.12.0, clean room)
--
-- scry__doc         — knowledge-graph entries (@scry.entry)
-- scry__doc_tag     — tags as join table (queryable, FTS-indexed)
-- scry__doc_seeded_question — seeded questions join table
-- scry__anchor      — named code-location bookmarks (@scry.anchor)
-- scry__anchor_seeded_question — anchor seeded questions
-- scry__rel         — typed edges between docs (depends_on, implements, supersedes)
-- scry__bind        — binding markers (@scry.bind), links source to target
-- scry__warning     — lint-style warnings (misplaced_doc, depends_on_cycle)

-- ---------------------------------------------------------------
-- scry__doc
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__doc (
  id           TEXT PRIMARY KEY,
  kind         TEXT NOT NULL DEFAULT 'internal',
  summary      TEXT NOT NULL DEFAULT '',
  rationale    TEXT,
  applies      TEXT,
  status       TEXT NOT NULL DEFAULT 'active',
  weight       REAL NOT NULL DEFAULT 0.5,
  current_path TEXT,
  content_hash TEXT,
  ephemeral    INTEGER NOT NULL DEFAULT 0,
  missing_since TEXT,
  -- extras: JSON-text serialization of the marker's `extras` field
  -- (scry-spec FR4.B, v1.1.0). Single-depth scalar map; NULL when absent.
  -- Query with SQLite JSON1 (json_extract, ->>, json_each).
  extras       TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_doc_kind   ON scry__doc(kind);
CREATE INDEX IF NOT EXISTS idx_doc_status ON scry__doc(status);
CREATE INDEX IF NOT EXISTS idx_doc_path   ON scry__doc(current_path);

-- FTS: id, summary, rationale, applies, current_path
CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_fts USING fts5(
  id, summary, rationale, applies, current_path,
  content='scry__doc', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS scry__doc_ai AFTER INSERT ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(rowid, id, summary, rationale, applies, current_path)
  VALUES (new.rowid, new.id, new.summary, new.rationale, new.applies, new.current_path);
END;

CREATE TRIGGER IF NOT EXISTS scry__doc_ad AFTER DELETE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, rationale, applies, current_path)
  VALUES ('delete', old.rowid, old.id, old.summary, old.rationale, old.applies, old.current_path);
END;

CREATE TRIGGER IF NOT EXISTS scry__doc_au AFTER UPDATE ON scry__doc BEGIN
  INSERT INTO scry__doc_fts(scry__doc_fts, rowid, id, summary, rationale, applies, current_path)
  VALUES ('delete', old.rowid, old.id, old.summary, old.rationale, old.applies, old.current_path);
  INSERT INTO scry__doc_fts(rowid, id, summary, rationale, applies, current_path)
  VALUES (new.rowid, new.id, new.summary, new.rationale, new.applies, new.current_path);
END;

-- ---------------------------------------------------------------
-- scry__doc_tag
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__doc_tag (
  doc_id TEXT NOT NULL REFERENCES scry__doc(id) ON DELETE CASCADE,
  tag    TEXT NOT NULL,
  PRIMARY KEY (doc_id, tag)
);
CREATE INDEX IF NOT EXISTS idx_tag_to_doc ON scry__doc_tag(tag);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_tag_fts USING fts5(
  tag, doc_id UNINDEXED
);

-- ---------------------------------------------------------------
-- scry__doc_seeded_question
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__doc_seeded_question (
  doc_id   TEXT    NOT NULL REFERENCES scry__doc(id) ON DELETE CASCADE,
  ordinal  INTEGER NOT NULL,
  question TEXT    NOT NULL,
  PRIMARY KEY (doc_id, ordinal)
);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__doc_seeded_question_fts USING fts5(
  question, doc_id UNINDEXED
);

-- ---------------------------------------------------------------
-- scry__anchor
--
-- id:      'name~hash' anchor identifier
-- doc_id:  FK to owning doc (nullable — files without a doc marker still
--          get their anchors indexed, just without an FK)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__anchor (
  id           TEXT PRIMARY KEY,
  doc_id       TEXT REFERENCES scry__doc(id) ON DELETE CASCADE,
  description  TEXT,
  content_hash TEXT,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_anchor_doc ON scry__anchor(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__anchor_fts USING fts5(
  id, description,
  content='scry__anchor', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS scry__anchor_ai AFTER INSERT ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(rowid, id, description)
  VALUES (new.rowid, new.id, new.description);
END;

CREATE TRIGGER IF NOT EXISTS scry__anchor_ad AFTER DELETE ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(scry__anchor_fts, rowid, id, description)
  VALUES ('delete', old.rowid, old.id, old.description);
END;

CREATE TRIGGER IF NOT EXISTS scry__anchor_au AFTER UPDATE ON scry__anchor BEGIN
  INSERT INTO scry__anchor_fts(scry__anchor_fts, rowid, id, description)
  VALUES ('delete', old.rowid, old.id, old.description);
  INSERT INTO scry__anchor_fts(rowid, id, description)
  VALUES (new.rowid, new.id, new.description);
END;

-- ---------------------------------------------------------------
-- scry__anchor_seeded_question
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__anchor_seeded_question (
  anchor_id TEXT    NOT NULL REFERENCES scry__anchor(id) ON DELETE CASCADE,
  ordinal   INTEGER NOT NULL,
  question  TEXT    NOT NULL,
  PRIMARY KEY (anchor_id, ordinal)
);

-- ---------------------------------------------------------------
-- scry__rel  (unified relationship table)
--
-- predicate: 'depends_on' | 'implements' | 'supersedes'
-- fragment:  '#FR3' loose-ref locator; empty string for whole-doc
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__rel (
  from_id   TEXT NOT NULL REFERENCES scry__doc(id) ON DELETE CASCADE,
  to_id     TEXT NOT NULL,
  predicate TEXT NOT NULL,
  fragment  TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (from_id, to_id, predicate, fragment)
);
CREATE INDEX IF NOT EXISTS idx_rel_to             ON scry__rel(to_id);
CREATE INDEX IF NOT EXISTS idx_rel_predicate      ON scry__rel(predicate);
CREATE INDEX IF NOT EXISTS idx_rel_from_predicate ON scry__rel(from_id, predicate);

-- ---------------------------------------------------------------
-- scry__bind
--
-- source_doc_id:   FK to owning doc (nullable)
-- source_local_id: the local bind marker id in the source file
-- target_id:       referenced doc/anchor id (ref before '#')
-- target_fragment: '#FR3' or '' for whole-doc
-- UNIQUE on (source_local_id, target_id, target_fragment) — comma-expanded
--           binds produce distinct rows; file-scoped local_id + target is
--           the natural dedup key.
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__bind (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  source_doc_id   TEXT    REFERENCES scry__doc(id) ON DELETE CASCADE,
  source_local_id TEXT    NOT NULL,
  target_id       TEXT    NOT NULL,
  target_fragment TEXT    NOT NULL DEFAULT '',
  comment         TEXT,
  content_hash    TEXT,
  created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
  UNIQUE (source_local_id, target_id, target_fragment)
);
CREATE INDEX IF NOT EXISTS idx_bind_source ON scry__bind(source_doc_id);
CREATE INDEX IF NOT EXISTS idx_bind_target ON scry__bind(target_id);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__bind_fts USING fts5(
  source_local_id, target_id, comment,
  content='scry__bind', content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS scry__bind_ai AFTER INSERT ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(rowid, source_local_id, target_id, comment)
  VALUES (new.rowid, new.source_local_id, new.target_id, new.comment);
END;

CREATE TRIGGER IF NOT EXISTS scry__bind_ad AFTER DELETE ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(scry__bind_fts, rowid, source_local_id, target_id, comment)
  VALUES ('delete', old.rowid, old.source_local_id, old.target_id, old.comment);
END;

CREATE TRIGGER IF NOT EXISTS scry__bind_au AFTER UPDATE ON scry__bind BEGIN
  INSERT INTO scry__bind_fts(scry__bind_fts, rowid, source_local_id, target_id, comment)
  VALUES ('delete', old.rowid, old.source_local_id, old.target_id, old.comment);
  INSERT INTO scry__bind_fts(rowid, source_local_id, target_id, comment)
  VALUES (new.rowid, new.source_local_id, new.target_id, new.comment);
END;

-- ---------------------------------------------------------------
-- scry__warning  (lint-style: misplaced_doc, depends_on_cycle, etc.)
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__warning (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kind        TEXT NOT NULL,
  marker_kind TEXT NOT NULL,
  marker_id   TEXT,
  file_path   TEXT NOT NULL,
  message     TEXT,
  detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_warning_path ON scry__warning(file_path);
CREATE INDEX IF NOT EXISTS idx_warning_kind ON scry__warning(kind);

-- ---------------------------------------------------------------
-- scry__file  (universal file-body index)
--
-- path:          repo-relative path (PK)
-- doc_id:        FK to scry__doc — nullable; unmarked files have NULL.
--                ON DELETE SET NULL: body stays searchable even after
--                marker removal.
-- body:          full file text for FTS
-- content_hash:  skip re-index when unchanged
-- last_modified: wall-clock of last watcher upsert
-- ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scry__file (
  path          TEXT PRIMARY KEY,
  doc_id        TEXT REFERENCES scry__doc(id) ON DELETE SET NULL,
  body          TEXT NOT NULL,
  content_hash  TEXT,
  last_modified TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_file_doc ON scry__file(doc_id);

CREATE VIRTUAL TABLE IF NOT EXISTS scry__file_fts USING fts5(
  path, body,
  content='scry__file', content_rowid='rowid',
  tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS scry__file_ai AFTER INSERT ON scry__file BEGIN
  INSERT INTO scry__file_fts(rowid, path, body) VALUES (new.rowid, new.path, new.body);
END;

CREATE TRIGGER IF NOT EXISTS scry__file_ad AFTER DELETE ON scry__file BEGIN
  INSERT INTO scry__file_fts(scry__file_fts, rowid, path, body)
  VALUES ('delete', old.rowid, old.path, old.body);
END;

CREATE TRIGGER IF NOT EXISTS scry__file_au AFTER UPDATE ON scry__file BEGIN
  INSERT INTO scry__file_fts(scry__file_fts, rowid, path, body)
  VALUES ('delete', old.rowid, old.path, old.body);
  INSERT INTO scry__file_fts(rowid, path, body) VALUES (new.rowid, new.path, new.body);
END;

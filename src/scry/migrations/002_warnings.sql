-- Warnings table for location-based misplacement and other lint-style issues.

CREATE TABLE IF NOT EXISTS scry__warning (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,             -- e.g. 'misplaced_doc', 'misplaced_file'
  marker_kind TEXT NOT NULL,      -- 'doc' | 'file' | 'anchor' | 'impl' | 'test'
  marker_id TEXT,                 -- the marker id (or anchor name)
  file_path TEXT NOT NULL,
  message TEXT,
  detected_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS scry__warning_path_idx ON scry__warning(file_path);
CREATE INDEX IF NOT EXISTS scry__warning_kind_idx ON scry__warning(kind);

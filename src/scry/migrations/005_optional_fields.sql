-- Migration 005: spec-optional fields — implements, supersedes, depends_on
--
-- Adds `implements` and `supersedes` TEXT columns to scry__doc so the
-- truly-optional scry-spec v1.0 fields (FR_OPT1–FR_OPT3) are queryable.
--
-- `depends_on` is stored in the existing doc_relationship table (not in
-- scry__doc); this migration does not touch doc_relationship.
--
-- The surface pipeline (upsert_doc + reindex_file) is updated separately
-- to auto-populate these columns and doc_relationship from parsed markers.
--
-- SQLite supports ADD COLUMN without a full table recreate when the new
-- column has no constraints or a constant default.

ALTER TABLE scry__doc ADD COLUMN implements TEXT;
ALTER TABLE scry__doc ADD COLUMN supersedes TEXT;

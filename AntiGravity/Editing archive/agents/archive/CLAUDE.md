# ARCHIVE Agent

## Responsibility
Write merged analysis JSON to SQLite. Validate tags against closed ontology.

## Key Files
- `writer.py` — `write_merged(merged, source_path) → clip_id`

## Database
- Path: `ARCHIVE_DB` env var (default `/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db`)
- Schema: `clips`, `segments`, `tags`, `feedback`, `exports`
- Initialize: `python scripts/init_db.py`

## Closed Ontology
Tags not in the ontology are **silently dropped** (logged as WARNING). Never pass unknown tags to the DB.

## Rules
- Parameterized queries only — no string interpolation in SQL.
- `write_merged` is idempotent per call but NOT per run (each call inserts a new clip row).

## Acceptance Criteria
`tests/test_archive_writer.py` — inserts a test clip + segment + 8 tags, verifies queryability.

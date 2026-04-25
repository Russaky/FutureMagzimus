"""Initialize SQLite database with Magzimus archive schema."""
import os, sqlite3, sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

DB_PATH = Path(os.getenv("ARCHIVE_DB", "/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  source_path TEXT NOT NULL,
  event_type TEXT NOT NULL,
  duration_seconds REAL,
  source_fps INTEGER,
  part_index INTEGER,
  total_parts INTEGER,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clip_id INTEGER REFERENCES clips(id),
  tc_start TEXT NOT NULL,
  tc_peak TEXT,
  tc_end TEXT NOT NULL,
  gemini_raw JSON,
  description TEXT,
  scores_audio REAL,
  scores_performance REAL,
  scores_final REAL,
  failure_detected BOOLEAN DEFAULT 0,
  critic_flag TEXT,
  analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  segment_id INTEGER REFERENCES segments(id),
  layer TEXT NOT NULL,
  tag TEXT NOT NULL,
  confidence TEXT DEFAULT 'medium'
);

CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  segment_id INTEGER REFERENCES segments(id),
  user_description TEXT,
  gemini_description TEXT,
  delta TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS exports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  segment_id INTEGER REFERENCES segments(id),
  position INTEGER,
  tc_used TEXT,
  output_path TEXT,
  exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);
CREATE INDEX IF NOT EXISTS idx_tags_layer ON tags(layer);
CREATE INDEX IF NOT EXISTS idx_segments_clip ON segments(clip_id);
CREATE INDEX IF NOT EXISTS idx_segments_scores ON segments(scores_final);
"""


def init_db(db_path: Path = DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"PASS: Database initialized — {db_path}")


if __name__ == "__main__":
    init_db()

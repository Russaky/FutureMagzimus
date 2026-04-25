"""Test ARCHIVE writer — init DB and write merged JSON to SQLite."""
import os, sys, sqlite3, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

DB_PATH      = Path(os.getenv("ARCHIVE_DB", "/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db"))
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))

SAMPLE_MERGED = {
    "clip_meta": {
        "source_file":      "_archive_test.mp4",
        "event_type":       "test_event",
        "part_index":       1,
        "total_parts":      1,
        "duration_seconds": 35.0,
        "source_fps":       25,
    },
    "segments": [
        {
            "tc_start":          "00:00:00",
            "tc_peak":           "00:00:15",
            "tc_end":            "00:00:35",
            "content_tags":      ["fire_eating", "crowd_interaction"],
            "context_tags":      ["outdoor", "festival", "evening"],
            "edit_potential":    "hook",
            "performance_level": "high",
            "crowd_response":    "strong",
            "scores_audio":      0.7,
            "scores_performance": 0.85,
            "scores_final":      0.805,
            "failure_detected":  False,
            "critic_flag":       None,
            "description":       "Test segment: fire eating with crowd interaction.",
        }
    ]
}


def main():
    print("=== ARCHIVE Writer Test ===")

    # 1. Init DB
    from scripts.init_db import init_db
    init_db(DB_PATH)

    # 2. Write sample merged JSON
    from agents.archive.writer import write_merged
    clip_id = write_merged(SAMPLE_MERGED, source_path=str(ARCHIVE_ROOT / "raw" / "test_event" / "_archive_test.mp4"))
    print(f"PASS: Clip written — clip_id={clip_id}")

    # 3. Verify rows in DB
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    clip = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    assert clip, "FAIL: clip row not found"
    print(f"PASS: clips row — filename={clip['filename']} event_type={clip['event_type']}")

    segs = conn.execute("SELECT * FROM segments WHERE clip_id = ?", (clip_id,)).fetchall()
    assert len(segs) == 1, f"FAIL: expected 1 segment, got {len(segs)}"
    seg = segs[0]
    print(f"PASS: segment row — tc={seg['tc_start']}→{seg['tc_end']} score={seg['scores_final']}")

    tags = conn.execute("SELECT layer, tag FROM tags WHERE segment_id = ?", (seg["id"],)).fetchall()
    tag_list = [(t["layer"], t["tag"]) for t in tags]
    assert ("content", "fire_eating") in tag_list, "FAIL: fire_eating tag missing"
    assert ("context", "outdoor") in tag_list, "FAIL: outdoor tag missing"
    assert ("edit_potential", "hook") in tag_list, "FAIL: hook tag missing"
    print(f"PASS: {len(tags)} tag(s) written — {tag_list}")

    conn.close()

    # 4. Query test — filter by content_tag
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT s.id FROM segments s
           JOIN tags t ON t.segment_id = s.id
           WHERE t.layer = 'content' AND t.tag = 'fire_eating'"""
    ).fetchall()
    assert len(rows) >= 1, "FAIL: query by content_tag returned nothing"
    print(f"PASS: Query by content_tag=fire_eating returned {len(rows)} row(s)")
    conn.close()

    print("\n=== ARCHIVE writer test PASSED ===")


if __name__ == "__main__":
    main()

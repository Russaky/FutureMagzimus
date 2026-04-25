"""ARCHIVE writer — maps merged analysis JSON to SQLite."""
import json, logging, os, sqlite3
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("ARCHIVE_DB", "/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db"))

# Closed ontology validation sets
CONTENT_TAGS = {
    "fire_eating", "fire_breathing", "fire_juggling", "fire_staff", "fire_poi", "fire_wand",
    "knife_juggling", "glass_walking", "balance_act", "club_juggling", "hat_trick",
    "crowd_interaction", "child_on_stage", "volunteer_on_stage", "comedy_moment",
    "potion_show", "alchemy_theme", "clown_act", "pyrotechnic_burst", "smoke_effect", "dramatic_reveal"
}
CONTEXT_TAGS = {
    "indoor", "outdoor", "large_crowd", "small_crowd", "evening", "daytime",
    "birthday_party", "festival", "street_show", "stage_show", "school_event", "corporate_event",
    "hebrew_speaking", "english_speaking"
}
EDIT_POTENTIAL = {"hook", "body", "ending"}
PERFORMANCE_LEVEL = {"low", "medium", "high", "peak"}
CROWD_RESPONSE = {"silent", "mixed", "strong", "peak"}


def _validate_tag(tag: str, valid_set: set, field: str) -> Optional[str]:
    if tag in valid_set:
        return tag
    log.warning(f"Unknown {field} tag '{tag}' — skipped")
    return None


def write_merged(merged: dict, source_path: str = "") -> int:
    """
    Write a merged analysis JSON to SQLite.
    Returns clip_id.
    """
    meta = merged["clip_meta"]
    segments = merged.get("segments", [])

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.cursor()

        # Insert clip row
        cur.execute(
            """INSERT INTO clips (filename, source_path, event_type, duration_seconds, source_fps, part_index, total_parts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                meta["source_file"],
                source_path,
                meta["event_type"],
                meta.get("duration_seconds"),
                meta.get("source_fps", 25),
                meta.get("part_index", 1),
                meta.get("total_parts", 1),
            )
        )
        clip_id = cur.lastrowid
        log.info(f"Inserted clip id={clip_id}: {meta['source_file']}")

        for seg in segments:
            # Validate enum fields
            perf_level = _validate_tag(seg.get("performance_level", ""), PERFORMANCE_LEVEL, "performance_level")
            crowd_resp  = _validate_tag(seg.get("crowd_response", ""), CROWD_RESPONSE, "crowd_response")
            edit_pot    = _validate_tag(seg.get("edit_potential", ""), EDIT_POTENTIAL, "edit_potential")

            cur.execute(
                """INSERT INTO segments
                   (clip_id, tc_start, tc_peak, tc_end, gemini_raw, description,
                    scores_audio, scores_performance, scores_final, failure_detected, critic_flag)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clip_id,
                    seg.get("tc_start", "00:00:00"),
                    seg.get("tc_peak"),
                    seg.get("tc_end", "00:00:00"),
                    json.dumps(seg),
                    seg.get("description"),
                    seg.get("scores_audio"),
                    seg.get("scores_performance"),
                    seg.get("scores_final"),
                    1 if seg.get("failure_detected") else 0,
                    seg.get("critic_flag"),
                )
            )
            segment_id = cur.lastrowid

            # Insert content tags
            for tag in seg.get("content_tags", []):
                if _validate_tag(tag, CONTENT_TAGS, "content_tag"):
                    cur.execute(
                        "INSERT INTO tags (segment_id, layer, tag) VALUES (?, ?, ?)",
                        (segment_id, "content", tag)
                    )

            # Insert context tags
            for tag in seg.get("context_tags", []):
                if _validate_tag(tag, CONTEXT_TAGS, "context_tag"):
                    cur.execute(
                        "INSERT INTO tags (segment_id, layer, tag) VALUES (?, ?, ?)",
                        (segment_id, "context", tag)
                    )

            # Insert edit_potential and performance_level as tags
            if edit_pot:
                cur.execute(
                    "INSERT INTO tags (segment_id, layer, tag) VALUES (?, ?, ?)",
                    (segment_id, "edit_potential", edit_pot)
                )
            if perf_level:
                cur.execute(
                    "INSERT INTO tags (segment_id, layer, tag) VALUES (?, ?, ?)",
                    (segment_id, "performance_level", perf_level)
                )
            if crowd_resp:
                cur.execute(
                    "INSERT INTO tags (segment_id, layer, tag) VALUES (?, ?, ?)",
                    (segment_id, "crowd_response", crowd_resp)
                )

        conn.commit()
        log.info(f"Wrote {len(segments)} segment(s) for clip_id={clip_id}")
        return clip_id

    finally:
        conn.close()

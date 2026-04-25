"""Flask interface — filter UI and export for Magzimus Archive."""
import os, sqlite3, subprocess, uuid, logging
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

DB_PATH      = Path(os.getenv("ARCHIVE_DB", "/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db"))
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
EXPORTS_DIR  = ARCHIVE_ROOT / "exports"

app = Flask(__name__, template_folder="templates")

CONTENT_TAGS = [
    "fire_eating", "fire_breathing", "fire_juggling", "fire_staff", "fire_poi", "fire_wand",
    "knife_juggling", "glass_walking", "balance_act", "club_juggling", "hat_trick",
    "crowd_interaction", "child_on_stage", "volunteer_on_stage", "comedy_moment",
    "potion_show", "alchemy_theme", "clown_act", "pyrotechnic_burst", "smoke_effect", "dramatic_reveal"
]
CONTEXT_TAGS = [
    "indoor", "outdoor", "large_crowd", "small_crowd", "evening", "daytime",
    "birthday_party", "festival", "street_show", "stage_show", "school_event", "corporate_event",
    "hebrew_speaking", "english_speaking"
]


def _conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _get_event_types():
    with _conn() as conn:
        rows = conn.execute("SELECT DISTINCT event_type FROM clips ORDER BY event_type").fetchall()
    return [r["event_type"] for r in rows]


def _query_segments(filters: dict) -> list[dict]:
    """Build and run filtered segment query. Returns list of dicts."""
    params = []
    joins  = []
    wheres = []

    if filters.get("content_tag"):
        joins.append("JOIN tags ct ON ct.segment_id = s.id AND ct.layer = 'content'")
        wheres.append("ct.tag = ?")
        params.append(filters["content_tag"])

    if filters.get("context_tag"):
        joins.append("JOIN tags ctx ON ctx.segment_id = s.id AND ctx.layer = 'context'")
        wheres.append("ctx.tag = ?")
        params.append(filters["context_tag"])

    if filters.get("performance_level"):
        joins.append("JOIN tags pl ON pl.segment_id = s.id AND pl.layer = 'performance_level'")
        wheres.append("pl.tag = ?")
        params.append(filters["performance_level"])

    if filters.get("crowd_response"):
        joins.append("JOIN tags cr ON cr.segment_id = s.id AND cr.layer = 'crowd_response'")
        wheres.append("cr.tag = ?")
        params.append(filters["crowd_response"])

    if filters.get("event_type"):
        wheres.append("c.event_type = ?")
        params.append(filters["event_type"])

    if filters.get("min_score"):
        wheres.append("s.scores_final >= ?")
        params.append(float(filters["min_score"]))

    if filters.get("date_from"):
        wheres.append("DATE(s.analyzed_at) >= ?")
        params.append(filters["date_from"])

    if filters.get("date_to"):
        wheres.append("DATE(s.analyzed_at) <= ?")
        params.append(filters["date_to"])

    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    join_sql  = " ".join(joins)

    sql = f"""
        SELECT DISTINCT
            s.id as segment_id, s.tc_start, s.tc_peak, s.tc_end,
            s.scores_audio, s.scores_performance, s.scores_final,
            s.failure_detected, s.critic_flag, s.description,
            c.filename, c.source_path, c.event_type, c.part_index, c.total_parts
        FROM segments s
        JOIN clips c ON c.id = s.clip_id
        {join_sql}
        {where_sql}
        ORDER BY s.scores_final DESC
        LIMIT 500
    """

    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    results = []
    for r in rows:
        seg = dict(r)

        # Fetch tags for this segment
        with _conn() as conn:
            tags = conn.execute(
                "SELECT layer, tag FROM tags WHERE segment_id = ?", (seg["segment_id"],)
            ).fetchall()

        seg["content_tags"]  = [t["tag"] for t in tags if t["layer"] == "content"]
        seg["context_tags"]  = [t["tag"] for t in tags if t["layer"] == "context"]
        results.append(seg)

    return results


@app.route("/")
def index():
    filters = {
        "content_tag":       request.args.get("content_tag", ""),
        "context_tag":       request.args.get("context_tag", ""),
        "event_type":        request.args.get("event_type", ""),
        "performance_level": request.args.get("performance_level", ""),
        "crowd_response":    request.args.get("crowd_response", ""),
        "min_score":         request.args.get("min_score", ""),
        "date_from":         request.args.get("date_from", ""),
        "date_to":           request.args.get("date_to", ""),
    }
    segments    = _query_segments(filters)
    event_types = _get_event_types()
    return render_template(
        "index.html",
        segments=segments,
        filters=filters,
        content_tags=CONTENT_TAGS,
        context_tags=CONTEXT_TAGS,
        event_types=event_types,
    )


@app.route("/export", methods=["POST"])
def export():
    """Export selected segments as numbered MP4s using FFmpeg -c copy."""
    data        = request.get_json()
    segment_ids = [int(i) for i in data.get("segment_ids", [])]
    if not segment_ids:
        return jsonify({"error": "No segment_ids provided"}), 400

    session_id  = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    session_dir = EXPORTS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    exported = []
    errors   = []

    with _conn() as conn:
        for pos, seg_id in enumerate(segment_ids, start=1):
            row = conn.execute(
                """SELECT s.tc_start, s.tc_end, s.tc_peak, c.source_path, c.filename, c.event_type
                   FROM segments s JOIN clips c ON c.id = s.clip_id
                   WHERE s.id = ?""",
                (seg_id,)
            ).fetchone()

            if not row:
                errors.append(f"Segment {seg_id} not found")
                continue

            source = Path(row["source_path"])
            if not source.exists():
                # Try resolving from ARCHIVE_ROOT/raw/event_type/filename
                source = ARCHIVE_ROOT / "raw" / row["event_type"] / row["filename"]

            if not source.exists():
                errors.append(f"Source file not found for segment {seg_id}: {source}")
                continue

            stem       = Path(row["filename"]).stem
            out_name   = f"{pos:03d}_{stem}.mp4"
            out_path   = session_dir / out_name
            tc_used    = row["tc_start"]

            # Parse HH:MM:SS to seconds for -ss/-t
            def tc_to_sec(tc):
                h, m, s = tc.split(":")
                return int(h)*3600 + int(m)*60 + float(s)

            start_sec  = tc_to_sec(row["tc_start"])
            end_sec    = tc_to_sec(row["tc_end"])
            duration   = end_sec - start_sec

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start_sec),
                "-t",  str(duration),
                "-i",  str(source),
                "-c",  "copy",
                str(out_path)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                errors.append(f"FFmpeg failed for segment {seg_id}: {result.stderr[-200:]}")
                continue

            # Record export in DB
            conn.execute(
                """INSERT INTO exports (session_id, segment_id, position, tc_used, output_path)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, seg_id, pos, tc_used, str(out_path))
            )
            exported.append(out_name)

        conn.commit()

    msg = f"Exported {len(exported)} clip(s) to exports/{session_id}/"
    if errors:
        msg += f" | {len(errors)} error(s): " + "; ".join(errors[:3])

    return jsonify({"message": msg, "session_id": session_id, "files": exported, "errors": errors})


@app.route("/feedback", methods=["POST"])
def feedback():
    """
    FEEDBACK stage: save user description, compute delta vs Gemini, propose prompt update.
    POST JSON: {segment_id: int, user_description: str}
    """
    data = request.get_json()
    segment_id = data.get("segment_id")
    user_desc  = (data.get("user_description") or "").strip()

    if not segment_id or not user_desc:
        return jsonify({"error": "segment_id and user_description required"}), 400

    with _conn() as conn:
        row = conn.execute(
            "SELECT description FROM segments WHERE id = ?", (segment_id,)
        ).fetchone()

    if not row:
        return jsonify({"error": f"Segment {segment_id} not found"}), 404

    gemini_desc = row["description"] or ""
    delta = _compute_delta(user_desc, gemini_desc)

    with _conn() as conn:
        conn.execute(
            """INSERT INTO feedback (segment_id, user_description, gemini_description, delta)
               VALUES (?, ?, ?, ?)""",
            (segment_id, user_desc, gemini_desc, delta)
        )
        conn.commit()

    prompt_suggestion = _suggest_prompt_update(user_desc, gemini_desc, delta)
    log.info(f"Feedback saved for segment {segment_id}")

    return jsonify({
        "saved": True,
        "gemini_description": gemini_desc,
        "delta": delta,
        "prompt_suggestion": prompt_suggestion,
    })


def _compute_delta(user_desc: str, gemini_desc: str) -> str:
    """Return a plain-text diff summary between two descriptions."""
    import difflib
    user_words   = set(user_desc.lower().split())
    gemini_words = set(gemini_desc.lower().split())
    missed  = user_words - gemini_words
    extra   = gemini_words - user_words
    parts = []
    if missed:
        parts.append(f"User mentioned, Gemini missed: {', '.join(sorted(missed)[:10])}")
    if extra:
        parts.append(f"Gemini added, user didn't: {', '.join(sorted(extra)[:10])}")
    return " | ".join(parts) if parts else "No significant delta"


def _suggest_prompt_update(user_desc: str, gemini_desc: str, delta: str) -> str:
    """Generate a prompt amendment suggestion based on the feedback delta."""
    if "No significant delta" in delta:
        return "Gemini description matches user — no prompt change needed."
    missed_part = ""
    for part in delta.split(" | "):
        if part.startswith("User mentioned, Gemini missed:"):
            missed_part = part.replace("User mentioned, Gemini missed:", "").strip()
    if missed_part:
        return (
            f"Consider adding to the documentary/performance prompt: "
            f"'Pay special attention to: {missed_part}. "
            f"These elements are important to the user.'"
        )
    return f"Review prompt for: {delta}"


@app.route("/analyze", methods=["POST"])
def analyze():
    """
    Trigger analysis + archive for an already-ingested payload.
    Accepts the same JSON payload as the n8n webhook.
    Used for direct triggering or n8n callback.
    """
    import threading
    payload = request.get_json()
    required = {"gcs_path", "gcs_audio_path", "source_file", "event_type", "part_index", "total_parts"}
    missing = required - set(payload.keys())
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    def _run():
        from agents.analysis.pipeline import run_analysis
        from agents.archive.writer import write_merged
        from scripts.init_db import init_db
        try:
            merged  = run_analysis(payload)
            init_db()
            clip_id = write_merged(merged, source_path=payload.get("source_file", ""))
            log.info(f"/analyze complete: clip_id={clip_id}")
        except Exception as e:
            log.error(f"/analyze failed: {e}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"accepted": True, "message": "Analysis queued in background"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

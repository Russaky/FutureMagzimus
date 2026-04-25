"""Full pipeline orchestrator: INGEST → ANALYSIS → ARCHIVE."""
import logging, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))


def run(input_path: Path, event_type: str) -> dict:
    """
    Run the full pipeline for a single video file.
    Returns {"clip_id": int, "segments": int, "merged": dict} on success.
    """
    from agents.ingest.pipeline import run_pipeline
    from agents.analysis.pipeline import run_analysis
    from agents.archive.writer import write_merged
    from scripts.init_db import init_db

    log.info(f"=== Orchestrator start: {input_path.name} | event={event_type} ===")

    # INGEST
    log.info("[1/3] INGEST")
    ingest_payloads = run_pipeline(input_path, event_type)

    results = []
    for payload in ingest_payloads:
        part = payload["part_index"]
        total = payload["total_parts"]
        log.info(f"[2/3] ANALYSIS — part {part}/{total}")

        try:
            merged = run_analysis(payload)
        except Exception as e:
            log.error(f"Analysis failed for part {part}: {e}")
            continue

        log.info(f"[3/3] ARCHIVE — part {part}/{total}")
        init_db()
        try:
            source_path = str(input_path)
            clip_id = write_merged(merged, source_path=source_path)
        except Exception as e:
            log.error(f"Archive write failed for part {part}: {e}")
            continue

        log.info(f"Part {part}/{total} complete — clip_id={clip_id}")
        results.append({
            "clip_id": clip_id,
            "part_index": part,
            "segments": len(merged.get("segments", [])),
        })

    log.info(f"=== Orchestrator done: {len(results)}/{len(ingest_payloads)} part(s) archived ===")
    return results

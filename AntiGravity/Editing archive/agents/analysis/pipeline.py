"""ANALYSIS pipeline: Audio → Performance → Documentary → Critic → GCS merged/."""
import json, logging, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

from agents.analysis import audio_agent, performance_agent, documentary_agent, critic_agent
from agents.ingest.gcs_uploader import upload_to_gcs

log = logging.getLogger(__name__)

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
GCS_BUCKET   = os.getenv("GCS_BUCKET", "magzimus-video-raw")


def run_analysis(payload: dict) -> dict:
    """
    Run full analysis pipeline from an ingest webhook payload.
    payload keys: gcs_path, gcs_audio_path, source_file, event_type,
                  part_index, total_parts, duration_seconds, source_fps
    Returns merged JSON dict.
    """
    gcs_video_uri = payload["gcs_path"]
    gcs_audio_uri = payload["gcs_audio_path"]

    clip_meta = {
        "source_file":      payload["source_file"],
        "event_type":       payload["event_type"],
        "part_index":       payload["part_index"],
        "total_parts":      payload["total_parts"],
        "duration_seconds": payload["duration_seconds"],
    }

    log.info(f"Analysis pipeline start: {clip_meta['source_file']} part {clip_meta['part_index']}/{clip_meta['total_parts']}")

    # 1. Audio agent
    audio_result = audio_agent.run(gcs_audio_uri)

    # 2. Performance agent (receives audio context)
    perf_result = performance_agent.run(gcs_video_uri, audio_result)

    # 3. Documentary agent (receives audio + performance context)
    doc_result = documentary_agent.run(gcs_video_uri, audio_result, perf_result)

    # 4. Critic merge
    merged = critic_agent.run(clip_meta, audio_result, perf_result, doc_result)

    # 5. Write merged JSON to GCS
    stem = Path(payload["source_file"]).stem
    part = f"part{payload['part_index']:03d}"
    merged_filename = f"{stem}_{part}_merged.json"

    merged_local = ARCHIVE_ROOT / "merged" / payload["event_type"] / merged_filename
    merged_local.parent.mkdir(parents=True, exist_ok=True)
    merged_local.write_text(json.dumps(merged, indent=2))

    gcs_merged_path = f"merged/{payload['event_type']}/{merged_filename}"
    upload_to_gcs(merged_local, gcs_merged_path)

    log.info(f"Analysis complete: gs://{GCS_BUCKET}/{gcs_merged_path}")
    return merged

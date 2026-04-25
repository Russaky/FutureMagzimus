"""INGEST pipeline: FFmpeg proxy → GCS upload → n8n webhook."""
import os, subprocess, logging, math
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

from agents.ingest.gcs_uploader import upload_to_gcs
from agents.ingest.webhook import send_webhook

log = logging.getLogger(__name__)

ARCHIVE_ROOT   = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
PROXY_LOW_DIR  = ARCHIVE_ROOT / "proxy" / "low_fps"
AUDIO_DIR      = ARCHIVE_ROOT / "audio"
CHUNK_DURATION = 600   # seconds
OVERLAP        = 30    # seconds
GCS_BUCKET     = os.getenv("GCS_BUCKET", "magzimus-video-raw")
ENVIRONMENT    = os.getenv("ENVIRONMENT", "TEST")


def get_duration(input_path: Path) -> float:
    """Return video duration in seconds via ffprobe."""
    result = subprocess.run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(input_path)
    ], capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def make_proxy_chunk(input_path: Path, output_path: Path, start: float, duration: float):
    """Create a single proxy chunk with proven FFmpeg parameters."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(input_path),
        "-vf", "scale=-2:480,fps=25",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "128k",
        "-write_tmcd", "0",
        "-copyts",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg proxy failed:\n{result.stderr[-500:]}")
    log.info(f"Proxy chunk created: {output_path.name}")


def extract_audio(input_path: Path, output_path: Path, start: float, duration: float):
    """Extract WAV mono 16kHz audio chunk."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", str(input_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio failed:\n{result.stderr[-500:]}")
    log.info(f"Audio chunk created: {output_path.name}")


def run_pipeline(input_path: Path, event_type: str) -> list:
    """
    Full ingest pipeline for one video file.
    Returns list of webhook payloads (one per chunk) for downstream use.
    """
    stem = input_path.stem
    log.info(f"Pipeline start: {input_path.name} | event_type={event_type}")

    duration = get_duration(input_path)
    log.info(f"Duration: {duration:.1f}s")

    total_parts = math.ceil(duration / CHUNK_DURATION)
    log.info(f"Splitting into {total_parts} chunk(s) of {CHUNK_DURATION}s with {OVERLAP}s overlap")

    payloads = []

    for i in range(total_parts):
        part_index = i + 1
        start = max(0, i * CHUNK_DURATION - (OVERLAP if i > 0 else 0))
        chunk_dur = min(CHUNK_DURATION + OVERLAP, duration - start)

        chunk_name = f"{stem}_part{part_index:03d}.mp4"
        audio_name = f"{stem}_part{part_index:03d}.wav"

        proxy_path = PROXY_LOW_DIR / event_type / chunk_name
        audio_path = AUDIO_DIR / event_type / audio_name

        # 1. Create proxy
        log.info(f"[{part_index}/{total_parts}] Creating proxy...")
        make_proxy_chunk(input_path, proxy_path, start, chunk_dur)

        # 2. Extract audio
        log.info(f"[{part_index}/{total_parts}] Extracting audio...")
        extract_audio(input_path, audio_path, start, chunk_dur)

        # 3. Upload proxy to GCS
        gcs_proxy_path = f"gs://{GCS_BUCKET}/Proxy_files/{event_type}/{chunk_name}"
        log.info(f"[{part_index}/{total_parts}] Uploading proxy to GCS...")
        upload_to_gcs(proxy_path, f"Proxy_files/{event_type}/{chunk_name}")

        # 4. Upload audio to GCS
        gcs_audio_path = f"gs://{GCS_BUCKET}/Audio/{event_type}/{audio_name}"
        log.info(f"[{part_index}/{total_parts}] Uploading audio to GCS...")
        upload_to_gcs(audio_path, f"Audio/{event_type}/{audio_name}")

        # 5. Send webhook to n8n (notification only)
        payload = {
            "gcs_path": gcs_proxy_path,
            "gcs_audio_path": gcs_audio_path,
            "source_file": input_path.name,
            "event_type": event_type,
            "part_index": part_index,
            "total_parts": total_parts,
            "duration_seconds": chunk_dur,
            "source_fps": 25,
            "environment": ENVIRONMENT
        }
        log.info(f"[{part_index}/{total_parts}] Sending webhook...")
        send_webhook(payload)
        payloads.append(payload)
        log.info(f"[{part_index}/{total_parts}] Done.")

    log.info(f"Pipeline complete: {input_path.name} — {total_parts} part(s) processed.")
    return payloads

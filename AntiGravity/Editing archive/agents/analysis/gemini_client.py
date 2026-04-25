"""Shared Gemini client for analysis agents."""
import os, json, re, logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

GEMINI_MODEL = "gemini-2.0-flash"
ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
GCS_BUCKET   = os.getenv("GCS_BUCKET", "magzimus-video-raw")

# Session-level cache: gcs_uri → gemini file name (valid for 48h)
_file_cache: dict[str, str] = {}

_GCS_TO_LOCAL = {
    f"gs://{GCS_BUCKET}/Audio/":       str(ARCHIVE_ROOT / "audio") + "/",
    f"gs://{GCS_BUCKET}/Proxy_files/": str(ARCHIVE_ROOT / "proxy/low_fps") + "/",
}


def _get_client():
    from google import genai
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set in .env")
    return genai.Client(api_key=api_key)


def _gcs_to_local(gcs_uri: str) -> Optional[Path]:
    """Map a GCS URI to its local counterpart if available."""
    for prefix, local_prefix in _GCS_TO_LOCAL.items():
        if gcs_uri.startswith(prefix):
            rel = gcs_uri[len(prefix):]
            return Path(local_prefix + rel)
    return None


def _upload_file(client, local_path: Path, mime_type: str) -> str:
    """Upload a local file to Gemini Files API, wait for ACTIVE state. Returns the file URI."""
    import time
    log.info(f"Uploading to Gemini Files API: {local_path.name}")
    uploaded = client.files.upload(
        file=local_path,
        config={"mime_type": mime_type, "display_name": local_path.name},
    )
    # Poll until file is ACTIVE (video files need processing time)
    for _ in range(30):
        file_info = client.files.get(name=uploaded.name)
        state = str(file_info.state)
        if "ACTIVE" in state:
            log.info(f"Uploaded and active: {file_info.uri}")
            return file_info.uri
        if "FAILED" in state:
            raise RuntimeError(f"Gemini file upload failed: {file_info.name}")
        log.debug(f"File state: {state} — waiting...")
        time.sleep(3)
    raise RuntimeError(f"Gemini file never became ACTIVE: {uploaded.name}")


def _resolve_file(client, gcs_uri: str, mime_type: str):
    """Return a Gemini Part for a GCS URI, uploading via Files API if needed."""
    from google.genai import types

    if gcs_uri in _file_cache:
        return types.Part.from_uri(file_uri=_file_cache[gcs_uri], mime_type=mime_type)

    local = _gcs_to_local(gcs_uri)
    if local and local.exists():
        gemini_uri = _upload_file(client, local, mime_type)
        _file_cache[gcs_uri] = gemini_uri
        return types.Part.from_uri(file_uri=gemini_uri, mime_type=mime_type)

    # Fallback: download from GCS then upload
    import tempfile
    from google.cloud import storage as gcs
    log.info(f"Local file not found — downloading from GCS: {gcs_uri}")
    bucket_name, blob_path = gcs_uri[5:].split("/", 1)
    gcs_client = gcs.Client()
    blob = gcs_client.bucket(bucket_name).blob(blob_path)
    suffix = Path(blob_path).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    blob.download_to_filename(str(tmp_path))
    gemini_uri = _upload_file(client, tmp_path, mime_type)
    tmp_path.unlink(missing_ok=True)
    _file_cache[gcs_uri] = gemini_uri
    return types.Part.from_uri(file_uri=gemini_uri, mime_type=mime_type)


def call_gemini(prompt: str, gcs_uris: list[tuple[str, str]] = None) -> dict:
    """
    Call Gemini with a text prompt and optional GCS media URIs.
    gcs_uris: list of (uri, mime_type) tuples e.g. [("gs://bucket/file.wav", "audio/wav")]
    Files are uploaded via Gemini Files API (standard API key, no Vertex AI required).
    Returns parsed JSON dict.
    """
    client = _get_client()
    parts = []

    if gcs_uris:
        for uri, mime_type in gcs_uris:
            parts.append(_resolve_file(client, uri, mime_type))

    parts.append(prompt)

    resp = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
    )

    text = resp.text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    return json.loads(text)

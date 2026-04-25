"""GCS upload helper for INGEST agent."""
import os, logging
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

GCS_BUCKET = os.getenv("GCS_BUCKET", "magzimus-video-raw")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")


def _get_client():
    from google.cloud import storage
    if GOOGLE_APPLICATION_CREDENTIALS:
        return storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
    return storage.Client()  # fallback to ADC


def upload_to_gcs(local_path: Path, gcs_object_name: str) -> str:
    """Upload local_path to GCS. Returns gs:// URI."""
    client = _get_client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(gcs_object_name)
    blob.upload_from_filename(str(local_path))
    uri = f"gs://{GCS_BUCKET}/{gcs_object_name}"
    log.info(f"Uploaded: {uri}")
    return uri

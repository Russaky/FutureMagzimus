"""Webhook sender for INGEST agent → n8n."""
import os, logging, requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env")

log = logging.getLogger(__name__)

ENVIRONMENT       = os.getenv("ENVIRONMENT", "TEST")
WEBHOOK_PROD      = os.getenv("N8N_WEBHOOK_PROD")
WEBHOOK_TEST      = os.getenv("N8N_WEBHOOK_TEST")
MAX_RETRIES       = 3


def send_webhook(payload: dict) -> bool:
    """Send payload to n8n webhook. Returns True on success."""
    url = WEBHOOK_TEST if ENVIRONMENT == "TEST" else WEBHOOK_PROD
    if not url:
        log.error("Webhook URL not configured in .env")
        return False

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=15)
            if resp.status_code in (200, 201):
                log.info(f"Webhook sent OK (attempt {attempt}): HTTP {resp.status_code}")
                return True
            log.warning(f"Webhook attempt {attempt} failed: HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Webhook attempt {attempt} error: {e}")

    log.error(f"Webhook failed after {MAX_RETRIES} attempts.")
    return False

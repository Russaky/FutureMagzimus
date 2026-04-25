"""Audio analysis agent — analyzes audio track via Gemini."""
import logging
from pathlib import Path

from agents.analysis.gemini_client import call_gemini

log = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "audio_agent.txt"


def run(gcs_audio_uri: str) -> dict:
    """Analyze audio from GCS WAV URI. Returns audio analysis dict."""
    prompt = PROMPT_PATH.read_text()
    log.info(f"Audio agent analyzing: {gcs_audio_uri}")
    result = call_gemini(prompt, gcs_uris=[(gcs_audio_uri, "audio/wav")])
    log.info(f"Audio agent: {len(result.get('segments', []))} segment(s)")
    return result

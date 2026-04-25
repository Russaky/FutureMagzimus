"""Performance analysis agent — analyzes visual performance via Gemini."""
import logging
from pathlib import Path

from agents.analysis.gemini_client import call_gemini

log = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "performance_agent.txt"


def run(gcs_video_uri: str, audio_result: dict) -> dict:
    """
    Analyze video performance from GCS MP4 URI.
    audio_result is passed as context in the prompt.
    Returns performance analysis dict.
    """
    import json
    prompt = PROMPT_PATH.read_text()
    prompt += f"\n\nAudio analysis context:\n{json.dumps(audio_result, indent=2)}"
    log.info(f"Performance agent analyzing: {gcs_video_uri}")
    result = call_gemini(prompt, gcs_uris=[(gcs_video_uri, "video/mp4")])
    log.info(f"Performance agent: {len(result.get('segments', []))} segment(s)")
    return result

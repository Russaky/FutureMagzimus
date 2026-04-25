"""Documentary context agent — analyzes setting and context via Gemini."""
import logging
from pathlib import Path

from agents.analysis.gemini_client import call_gemini

log = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "documentary_agent.txt"


def run(gcs_video_uri: str, audio_result: dict, performance_result: dict) -> dict:
    """
    Analyze documentary context from GCS MP4 URI.
    Prior agent outputs passed as context.
    Returns documentary analysis dict.
    """
    import json
    prompt = PROMPT_PATH.read_text()
    prompt += f"\n\nAudio analysis context:\n{json.dumps(audio_result, indent=2)}"
    prompt += f"\n\nPerformance analysis context:\n{json.dumps(performance_result, indent=2)}"
    log.info(f"Documentary agent analyzing: {gcs_video_uri}")
    result = call_gemini(prompt, gcs_uris=[(gcs_video_uri, "video/mp4")])
    log.info(f"Documentary agent: {len(result.get('segments', []))} segment(s)")
    return result

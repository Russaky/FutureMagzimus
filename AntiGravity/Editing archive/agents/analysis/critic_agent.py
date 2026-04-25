"""Critic/merge agent — merges all 3 analysis outputs into final JSON."""
import json, logging
from pathlib import Path

from agents.analysis.gemini_client import call_gemini

log = logging.getLogger(__name__)
PROMPT_PATH = Path(__file__).parents[2] / "prompts" / "critic_agent.txt"


def run(clip_meta: dict, audio_result: dict, performance_result: dict, documentary_result: dict) -> dict:
    """
    Merge outputs from all 3 agents into final unified segment JSON.
    Returns merged analysis dict with clip_meta and segments.
    """
    prompt = PROMPT_PATH.read_text()
    prompt += f"\n\nClip metadata:\n{json.dumps(clip_meta, indent=2)}"
    prompt += f"\n\nAudio analysis:\n{json.dumps(audio_result, indent=2)}"
    prompt += f"\n\nPerformance analysis:\n{json.dumps(performance_result, indent=2)}"
    prompt += f"\n\nDocumentary analysis:\n{json.dumps(documentary_result, indent=2)}"

    log.info("Critic agent merging analyses...")
    result = call_gemini(prompt)
    log.info(f"Critic agent: {len(result.get('segments', []))} merged segment(s)")
    return result

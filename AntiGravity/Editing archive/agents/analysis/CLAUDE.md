# ANALYSIS Agent

## Responsibility
Run 4 Gemini agents serially (Audio → Performance → Documentary → Critic), produce merged JSON, write to GCS `merged/`.

## Key Files
- `pipeline.py` — orchestrates the 4 agents. Entry: `run_analysis(payload) → merged_dict`
- `gemini_client.py` — shared Gemini client (Files API, session-level cache)
- `audio_agent.py` — analyzes WAV audio track
- `performance_agent.py` — analyzes visual performance (video + audio context)
- `documentary_agent.py` — analyzes setting/context (video + prior contexts)
- `critic_agent.py` — merges all 3 outputs into final segment JSON

## Prompts
All prompts live in `prompts/`. Never hardcode prompt text in agent code.

## Gemini Integration
- Uses `GEMINI_API_KEY` (standard Gemini API, not Vertex AI — see DECISIONS.md D-001)
- Media files uploaded via Files API (auto-maps GCS URIs to local paths)
- Files cached per Python session by GCS URI to avoid duplicate uploads
- File state is polled until ACTIVE before use

## Output Format
```json
{
  "clip_meta": {...},
  "segments": [
    {
      "tc_start": "HH:MM:SS", "tc_peak": "...", "tc_end": "...",
      "content_tags": [...], "context_tags": [...],
      "edit_potential": "hook|body|ending",
      "performance_level": "low|medium|high|peak",
      "crowd_response": "silent|mixed|strong|peak",
      "scores_audio": 0.0-1.0, "scores_performance": 0.0-1.0, "scores_final": 0.0-1.0,
      "failure_detected": bool, "critic_flag": str|null, "description": str
    }
  ]
}
```

## Acceptance Criteria
`tests/test_analysis_pipeline.py` — requires ingest test to have run first.

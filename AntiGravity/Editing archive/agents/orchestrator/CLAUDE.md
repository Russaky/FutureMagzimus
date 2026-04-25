# ORCHESTRATOR Agent

## Responsibility
Chain INGEST → ANALYSIS → ARCHIVE for a single video file. Called by the watcher.

## Entry Point
```python
from agents.orchestrator.pipeline import run
results = run(input_path, event_type)
# results: list of {"clip_id": int, "part_index": int, "segments": int}
```

## Flow
1. `ingest.pipeline.run_pipeline(path, event_type)` → list of payloads (one per chunk)
2. For each payload: `analysis.pipeline.run_analysis(payload)` → merged JSON
3. For each merged JSON: `archive.writer.write_merged(merged, source_path)` → clip_id

## Error Handling
- Analysis failure for one part is logged and skipped; other parts continue.
- Archive failure for one part is logged and skipped; other parts continue.
- Returns only successfully archived parts.

## No Acceptance Test
The orchestrator is tested indirectly via `test_ingest_pipeline.py` + `test_analysis_pipeline.py` + `test_archive_writer.py`. An end-to-end orchestrator test would require a 35s+ video and ~2 minutes of Gemini API calls.

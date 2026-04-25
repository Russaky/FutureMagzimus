# INGEST Agent

## Responsibility
Watch `raw/` for new video files, create proxy chunks, extract audio, upload both to GCS, send webhook to n8n.

## Key Files
- `watcher.py` — watchdog-based file monitor (entry point: `python -m agents.ingest.watcher`)
- `pipeline.py` — FFmpeg proxy + audio + GCS upload + webhook. Returns list of payloads.
- `gcs_uploader.py` — GCS upload helper
- `webhook.py` — POST to n8n webhook (TEST or PROD based on ENVIRONMENT)

## Rules
- Files in `raw/unsorted/` are logged but never processed.
- Wait for file to be stable (size unchanged for 5s, min 10MB) before processing.
- Chunks: 600s + 30s overlap. Single-part files (<600s) produce one chunk.
- All FFmpeg parameters are fixed. Do not change without testing on real footage.

## Acceptance Criteria
`tests/test_ingest_pipeline.py` — creates synthetic 35s video, runs full pipeline, verifies proxy + audio exist locally and in GCS.

## What This Agent Does NOT Do
- It does NOT run analysis or write to SQLite.
- It does NOT delete source files.
- n8n webhook is notification only — orchestrator chains analysis directly.

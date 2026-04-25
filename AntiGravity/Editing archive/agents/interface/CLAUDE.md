# INTERFACE Agent

## Responsibility
Flask web UI for querying the archive, exporting clips, and submitting feedback.

## Entry Point
```bash
python agents/interface/app.py
# Serves at http://127.0.0.1:5000
```

## Endpoints
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Filter UI — query segments by tag, score, date |
| POST | `/export` | Export selected segments as numbered MP4s |
| POST | `/feedback` | Submit user description, get delta + prompt suggestion |
| POST | `/analyze` | Queue analysis pipeline in background (for direct triggers) |

## Export
- Uses `ffmpeg -c copy` for lossless, fast extraction from source files.
- Output: `exports/{session_id}/{NNN}_{stem}.mp4`
- Source path falls back to `raw/{event_type}/{filename}` if stored path missing.

## Feedback
- Saves `(segment_id, user_description, gemini_description, delta)` to `feedback` table.
- Delta is word-set difference (see DECISIONS.md D-003).
- Returns prompt amendment suggestion.

## Security
- Bound to `127.0.0.1` only — never expose to public network.
- All DB queries use parameterized statements.
- No user input is passed to shell commands.

## Acceptance Criteria
`tests/test_interface.py` and `tests/test_feedback.py`

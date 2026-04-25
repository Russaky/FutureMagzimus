# Magzimus Archive — Cowork Startup Brief

## Your Role
You are the lead developer agent for the Magzimus Video Archive project.
You build, test, and maintain autonomously. You report to the user only when blocked.
You never ask for decisions that fall within your scope. You make them, document them, and move on.

---

## Project Goal
Build a searchable video archive that lets the user retrieve raw footage clips via natural language prompts — saving editing time and enabling content productivity.
**The archive is the product. Clips are a byproduct.**

---

## Paths

| Name | Path |
|---|---|
| Project root | `/Users/user/AntiGravity/Editing archive` |
| Archive root | `/Volumes/Magzimus_2T/Magzimus_Video_Archive` |
| Archive DB | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db` |
| Raw video | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/raw/` |
| Proxy low fps | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/proxy/low_fps/` |
| Proxy high fps | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/proxy/high_fps/` |
| Audio | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/audio/` |
| Exports | `/Volumes/Magzimus_2T/Magzimus_Video_Archive/exports/` |

---

## Day Zero — Do This First, In Order

### Step 1 — Create project structure
```bash
mkdir -p "/Users/user/AntiGravity/Editing archive"
cd "/Users/user/AntiGravity/Editing archive"
mkdir -p agents/{orchestrator,ingest,analysis,archive,interface,qa}
mkdir -p scripts prompts tests logs
```

### Step 2 — Create .gitignore immediately
```
.env
*.log
__pycache__/
*.pyc
.DS_Store
venv/
archive.db
```

### Step 3 — Create .env template (empty values — user fills in)
```bash
cat > .env.template << 'EOF'
GCS_BUCKET=magzimus-video-raw
GCS_REGION=me-west1
N8N_WEBHOOK_PROD=https://n8n.russak.cloud/webhook/6a1ed42a-4185-496d-a97d-6b57a623f7e0
N8N_WEBHOOK_TEST=https://n8n.russak.cloud/webhook-test/6a1ed42a-4185-496d-a97d-6b57a623f7e0
N8N_BASE_URL=https://n8n.russak.cloud
N8N_API_KEY=
GOOGLE_APPLICATION_CREDENTIALS=
ANTHROPIC_API_KEY=
ARCHIVE_DB=/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db
ARCHIVE_ROOT=/Volumes/Magzimus_2T/Magzimus_Video_Archive
ENVIRONMENT=TEST
EOF
```
**Pause here. Ask user to copy .env.template → .env and fill in all keys before continuing.**

### Step 4 — Create Python venv
```bash
python3 -m venv venv
source venv/bin/activate
pip install python-dotenv watchdog google-cloud-storage flask ffmpeg-python anthropic requests
pip freeze > requirements.txt
```

### Step 5 — Verify all connections (run each test separately)
```bash
python tests/test_gcs.py        # GCS read/write
python tests/test_n8n_api.py    # n8n API key + workflow list
python tests/test_n8n_webhook.py # webhook reachable
python tests/test_vertex.py     # Gemini API call
python tests/test_anthropic.py  # Claude API call
python tests/test_archive_drive.py # external drive mounted and writable
```
**All 6 must be green before writing any feature code.**

### Step 6 — Create archive directory structure
```bash
python scripts/setup_archive.py  # creates all dirs on external drive
```

### Step 7 — Write CLAUDE.md files for each agent subfolder
Each agent gets its own CLAUDE.md scoped to its responsibilities.

---

## Red Lines

1. **Never delete files you did not create.** Add to `TO_DELETE.md` and continue.
2. **3 attempts max on any single problem.** After 3 → write `BLOCKED.md` and stop. Do not attempt a 4th approach.
3. **Never print or log secrets.** Load from `.env` only. Never pass as CLI args.
4. **Never modify files outside project root and archive root.**
5. **Rollback before retry.** Git commit before every fix attempt.

---

## Rollback Convention
Before every fix attempt:
```bash
git add -A && git commit -m "pre-fix: [describe problem]"
```
If fix fails:
```bash
git revert HEAD
```
Then try next approach from clean state.

---

## Blocked Convention
When blocked after 3 attempts, create `BLOCKED.md`:
```markdown
## Blocked: [problem description]
**Date:** [timestamp]
**Attempt 1:** [what was tried, what happened]
**Attempt 2:** [what was tried, what happened]
**Attempt 3:** [what was tried, what happened]
**Current state:** [what is broken, what still works]
**Hypothesis:** [best guess at root cause]
**Files affected:** [list]
```
Stop all work. Do not attempt further fixes. Wait for user.

---

## Stage Acceptance Criteria

| Stage | Done When |
|---|---|
| INGEST | New file in raw/ → proxy created → GCS upload confirmed → webhook received by n8n |
| ANALYSIS | n8n receives webhook → 3 agents run serially → merged JSON written to GCS merged/ |
| ARCHIVE | merged JSON → SQLite rows written → queryable by content_tag and timecode |
| INTERFACE | Flask runs locally → filter UI loads → export produces numbered MP4s from source |
| FEEDBACK | User description saved → delta vs Gemini stored → prompt update proposed |

**Agent declares a stage complete only when its acceptance test passes — not when code runs.**

---

## Pipeline

### INGEST
- Monitor `raw/` subfolders with `watchdog`
- On new file: print folder name, wait for user confirmation in terminal
- `unsorted/` files: log to `logs/ingest.log`, do not process, wait
- FFmpeg proxy (proven parameters from V1):
```
ffmpeg -y -ss {start} -t {chunk_duration} -i {input}
  -vf "scale=-2:480,fps=25"
  -c:v libx264 -preset ultrafast -crf 30
  -c:a aac -b:a 128k
  -write_tmcd 0
  -copyts
  {output}
```
- Chunks: 600s, 30s overlap
- Audio: WAV mono 16kHz separate extract
- Webhook payload:
```json
{
  "gcs_path": "gs://magzimus-video-raw/Proxy_files/{filename}",
  "gcs_audio_path": "gs://magzimus-video-raw/Audio/{filename}",
  "source_file": "{original_filename}",
  "event_type": "{folder_name}",
  "part_index": 1,
  "total_parts": 3,
  "duration_seconds": 600,
  "source_fps": 25,
  "environment": "TEST|PROD"
}
```

### ANALYSIS (serial)
Order: Audio Agent → Performance Agent → Documentary Agent → Critic merge
Each agent receives output of previous as context.
Prompts live in `prompts/` — loaded at runtime, never hardcoded.

### ARCHIVE
- Claude API reads merged JSON
- Maps to closed ontology (see below)
- Writes to SQLite via parameterized queries only (no string interpolation)
- Every segment gets: tc_start, tc_peak, tc_end from source timecode

### INTERFACE
- Flask local only (127.0.0.1)
- Filter by: content_tag, event_type, performance score, crowd score, date range
- Export: FFmpeg `-c copy` from source file, numbered `001_name.mp4`

---

## Closed Ontology (Archive Tags)

### content_tags
```
fire_eating, fire_breathing, fire_juggling, fire_staff, fire_poi, fire_wand,
knife_juggling, glass_walking, balance_act, club_juggling, hat_trick,
crowd_interaction, child_on_stage, volunteer_on_stage, comedy_moment,
potion_show, alchemy_theme, clown_act, pyrotechnic_burst, smoke_effect, dramatic_reveal
```

### context_tags
```
indoor, outdoor, large_crowd, small_crowd, evening, daytime,
birthday_party, festival, street_show, stage_show, school_event, corporate_event,
hebrew_speaking, english_speaking
```

### edit_potential
```
hook, body, ending
```

### performance_level
```
low, medium, high, peak
```

### crowd_response
```
silent, mixed, strong, peak
```

---

## SQLite Schema

```sql
CREATE TABLE clips (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  filename TEXT NOT NULL,
  source_path TEXT NOT NULL,
  event_type TEXT NOT NULL,
  duration_seconds REAL,
  source_fps INTEGER,
  part_index INTEGER,
  total_parts INTEGER,
  ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE segments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  clip_id INTEGER REFERENCES clips(id),
  tc_start TEXT NOT NULL,
  tc_peak TEXT,
  tc_end TEXT NOT NULL,
  gemini_raw JSON,
  description TEXT,
  scores_audio REAL,
  scores_performance REAL,
  scores_final REAL,
  failure_detected BOOLEAN DEFAULT 0,
  critic_flag TEXT,
  analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  segment_id INTEGER REFERENCES segments(id),
  layer TEXT NOT NULL,
  tag TEXT NOT NULL,
  confidence TEXT DEFAULT 'medium'
);

CREATE TABLE feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  segment_id INTEGER REFERENCES segments(id),
  user_description TEXT,
  gemini_description TEXT,
  delta TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE exports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  segment_id INTEGER REFERENCES segments(id),
  position INTEGER,
  tc_used TEXT,
  output_path TEXT,
  exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tags_tag ON tags(tag);
CREATE INDEX idx_tags_layer ON tags(layer);
CREATE INDEX idx_segments_clip ON segments(clip_id);
CREATE INDEX idx_segments_scores ON segments(scores_final);
```

---

## n8n API Usage
Base URL: loaded from `N8N_BASE_URL` env var
Auth header: `X-N8N-API-KEY: {N8N_API_KEY}`
Never hardcode. Always load from env.

Useful endpoints:
- `GET /api/v1/workflows` — list workflows
- `GET /api/v1/workflows/{id}` — get workflow JSON
- `PUT /api/v1/workflows/{id}` — update workflow
- `POST /api/v1/workflows/{id}/activate` — activate
- `GET /api/v1/executions` — execution history

---

## Decision Rule
When facing an architectural decision not covered above:
**Default to whatever best serves archive searchability and user query speed.**
Document the decision in `DECISIONS.md` with rationale.

---

## Management Escalation
Escalate to user only for:
- All 3 fix attempts failed (write BLOCKED.md)
- External drive not mounted and cannot proceed
- n8n API returns auth error after key reload
- Schema change required that breaks existing data

Everything else: decide, document, continue.

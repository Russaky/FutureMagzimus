# Architecture Decisions

## D-001: Gemini Files API instead of Vertex AI GCS URIs

**Decision:** Use the standard Gemini API (`GEMINI_API_KEY`) with the Files API for media uploads, rather than Vertex AI with GCS URI references.

**Why:** Vertex AI access returned 404 NOT_FOUND for all models/regions on this project (`magzimusvideoagent`), indicating billing or model-access issue. The standard Gemini API with Files API is fully functional. Files are uploaded once per session (cached) and expire after 48h.

**Trade-off:** Files must be re-uploaded per session rather than referenced directly from GCS. Acceptable since analysis only runs when a new clip is ingested.

---

## D-002: Orchestrator chains INGEST → ANALYSIS → ARCHIVE directly

**Decision:** The orchestrator runs all three stages in a single Python process triggered by the file watcher. n8n receives the webhook (notification) but does not trigger analysis.

**Why:** n8n is cloud-hosted; the analysis pipeline is local. Making n8n call back to a local endpoint requires tunnel setup (ngrok, etc.) which adds fragility. Direct chaining is simpler and faster.

**Trade-off:** n8n is reduced to a notification layer for this version. If analysis is ever moved to a cloud service, the orchestrator would need to be split.

---

## D-003: FEEDBACK delta uses word-set comparison

**Decision:** Delta computation uses set difference on word tokens, not a semantic comparison.

**Why:** The purpose is to give the user a quick indication of what Gemini missed or invented. Semantic comparison would require another Gemini call, adding latency and cost. Word-set diff is instant and good enough for prompt amendment suggestions.

**Trade-off:** Does not catch paraphrases ("cheering" vs "applause"). Acceptable for V1.

---

## D-004: Python 3.9 compatibility — no union type syntax

**Decision:** All type hints use `Optional[X]` from typing, not `X | None` (Python 3.10+ syntax).

**Why:** The system Python on this machine is 3.9.6. The venv is based on 3.10 but the packages are loaded from the system 3.9 path.

---

## D-005: Ingest pipeline returns payload list

**Decision:** `ingest.pipeline.run_pipeline()` now returns a list of webhook payloads (one per chunk) instead of returning None.

**Why:** Allows the orchestrator to iterate over parts and chain analysis without duplicating the chunking logic.

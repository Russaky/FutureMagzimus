"""Trigger training sessions — persisted index of labeled recordings used to
train the motion classifier (motion_classifier.py). Each session just points
at a JSONL file already written by the existing /api/measure/* recording
machinery (control/server/app.py) — this store does not duplicate that data,
it only tags "this recording is a labeled example of trigger X".

Same atomic-write JSON-file CRUD pattern as bank_manager.BankStore /
effects_library.EffectStore (load-into-memory dict, tmp-file + os.replace,
no DB).
"""
from __future__ import annotations
import json
import os
import threading
import time
import uuid
from typing import Optional


class TriggerSessionStore:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}
        self._load()

    # ─── persistence ────────────────────────────────────────────────────────

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path) as f:
                    self._sessions = json.load(f).get('sessions', {})
            except Exception:
                self._sessions = {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'sessions': self._sessions}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    # ─── CRUD ───────────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        with self._lock:
            return [{'id': sid, **s} for sid, s in self._sessions.items()]

    def counts(self) -> dict[str, int]:
        """trigger -> number of recorded sessions, for the "N/20" UI nudge."""
        with self._lock:
            out: dict[str, int] = {}
            for s in self._sessions.values():
                out[s['trigger']] = out.get(s['trigger'], 0) + 1
            return out

    def create(self, trigger: str, file: str, frame_count: int) -> dict:
        with self._lock:
            sid = str(uuid.uuid4())[:8]
            self._sessions[sid] = {
                'trigger': trigger, 'file': file, 'frameCount': frame_count,
                'recordedAt': time.time(),
            }
            self._save()
            return {'id': sid, **self._sessions[sid]}

    def delete(self, session_id: str) -> Optional[str]:
        """Returns the deleted session's file name (caller may want to also
        remove the underlying JSONL), or None if not found."""
        with self._lock:
            s = self._sessions.pop(session_id, None)
            if s is None:
                return None
            self._save()
            return s['file']

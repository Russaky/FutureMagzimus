"""Effects Library — persisted, named, device-scoped LED effect presets.

An "Effect" is a saved preset for one output device type. `staff` effects all
go through the single generic parametric engine (templateId/paletteId or
custom RGB/speed/intensity/param1/param2 → EffectCommand, see
firmware/staff/include/LedManager.cpp genericEffect()) — the old separate
"legacy" fixed-CmdType family was folded into it (Solid/Sparkle/Rainbow/Flame/
Vertical all have generic-template equivalents now, see FX_* in Protocol.h).
`dmx`/`pwm`/`progressbar` only support a static color (+ fade where the
protocol has it) — no onboard effect engine exists for them yet.

Same JSON-file CRUD pattern as bank_manager.BankStore (atomic write, no DB).
"""
from __future__ import annotations
import json
import os
import threading
import time
import uuid
from typing import Optional

DEVICE_TYPES = ('staff', 'dmx', 'pwm', 'progressbar')


class EffectStore:
    def __init__(self, path: str):
        self._path = path
        self._lock = threading.Lock()
        self._effects: dict[str, dict] = {}
        self._load()

    # ─── persistence ────────────────────────────────────────────────────────

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path) as f:
                    self._effects = json.load(f).get('effects', {})
            except Exception:
                self._effects = {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'effects': self._effects}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    # ─── CRUD ───────────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        with self._lock:
            return [{'id': eid, **e} for eid, e in self._effects.items()]

    def get(self, effect_id: str) -> Optional[dict]:
        with self._lock:
            e = self._effects.get(effect_id)
            return {'id': effect_id, **e} if e else None

    def create(self, fields: dict) -> dict:
        with self._lock:
            effect_id = str(uuid.uuid4())[:8]
            now = time.time()
            self._effects[effect_id] = {**fields, 'createdAt': now, 'updatedAt': now}
            self._save()
            return {'id': effect_id, **self._effects[effect_id]}

    def update(self, effect_id: str, fields: dict) -> Optional[dict]:
        with self._lock:
            e = self._effects.get(effect_id)
            if e is None:
                return None
            e.update(fields)
            e['updatedAt'] = time.time()
            self._save()
            return {'id': effect_id, **e}

    def delete(self, effect_id: str) -> bool:
        with self._lock:
            existed = effect_id in self._effects
            self._effects.pop(effect_id, None)
            if existed:
                self._save()
            return existed

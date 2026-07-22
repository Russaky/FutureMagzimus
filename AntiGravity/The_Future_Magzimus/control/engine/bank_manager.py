"""Bank Manager — Active Bank state + fixed-trigger → action mapping.

A "Bank" is a named preset: for each of the 6 fixed staff-motion triggers
(Fast Spin, Toss, Roll, Catch, Static Horizontal, Static Vertical) it maps to
an optional action. Actions reuse the exact `timelines` list format already
used by Number events (device/policy/steps/targetId|targetSlot), so bank
actions are dispatched through Engine._fire_event() unchanged — no separate
execution path to keep in sync.
"""
from __future__ import annotations
import json
import os
import threading
import uuid
from typing import Optional

# Mirrors firmware/staff/include/Protocol.h MotionType
MOTION_IDLE, MOTION_SWING, MOTION_SPIN = 0, 1, 2

FAST_SPIN_SPEED_THRESHOLD = 8.0   # rad/s
STATIC_SPEED_THRESHOLD    = 1.5   # rad/s — below this the staff is considered still

FIXED_TRIGGERS = ['fast_spin', 'toss', 'roll', 'catch', 'static_horizontal', 'static_vertical']

# Default priority per fixed trigger (lower = wins conflicts / interrupts higher).
# Momentary, high-signal events (catch/toss) outrank continuous motion states
# (spin/roll), which in turn outrank passive stillness (static).
# 1 is highest priority, 6 is lowest.
DEFAULT_TRIGGER_PRIORITY = {
    'catch':             1,
    'toss':              2,
    'fast_spin':         3,
    'roll':              4,
    'static_vertical':   5,
    'static_horizontal': 6,
}


def eval_fixed_trigger(key: str, data: dict) -> bool:
    """Evaluate one of the 6 fixed Bank triggers against a staff_telemetry dict."""
    if data.get('_type') not in (None, 'staff_telemetry'):
        return False
    speed       = data.get('speed', 0.0) or 0.0
    motion      = data.get('motionType', MOTION_IDLE)
    orientation = data.get('orientation')

    if key == 'fast_spin':
        return motion == MOTION_SPIN and speed > FAST_SPIN_SPEED_THRESHOLD
    if key == 'toss':
        return bool(data.get('throw'))
    if key == 'roll':
        return motion == MOTION_SWING
    if key == 'catch':
        return bool(data.get('catch'))
    if key == 'static_horizontal':
        return speed < STATIC_SPEED_THRESHOLD and orientation == 'horizontal'
    if key == 'static_vertical':
        return speed < STATIC_SPEED_THRESHOLD and orientation == 'vertical'
    return False


class BankStore:
    """Persists Banks (trigger→action presets) to JSON and tracks the active one."""

    def __init__(self, path: str):
        self._path      = path
        self._lock      = threading.Lock()
        self._banks: dict[str, dict] = {}
        self._active_id: Optional[str] = None
        self._load()

    # ─── persistence ────────────────────────────────────────────────────────

    def _load(self):
        if os.path.isfile(self._path):
            try:
                with open(self._path) as f:
                    data = json.load(f)
                self._banks     = data.get('banks', {})
                self._active_id = data.get('active')
            except Exception:
                self._banks, self._active_id = {}, None
        # Migrate banks saved before priorities existed.
        for bank in self._banks.values():
            bank.setdefault('priorities', dict(DEFAULT_TRIGGER_PRIORITY))
            for key, default in DEFAULT_TRIGGER_PRIORITY.items():
                bank['priorities'].setdefault(key, default)

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        tmp = self._path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump({'active': self._active_id, 'banks': self._banks}, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self._path)

    # ─── CRUD ───────────────────────────────────────────────────────────────

    def list(self) -> list[dict]:
        with self._lock:
            return [{'id': bid, **b} for bid, b in self._banks.items()]

    def get(self, bank_id: str) -> Optional[dict]:
        with self._lock:
            b = self._banks.get(bank_id)
            return {'id': bank_id, **b} if b else None

    def create(self, name: str) -> dict:
        with self._lock:
            bank_id = str(uuid.uuid4())[:8]
            self._banks[bank_id] = {
                'name':     name,
                'mappings': {k: None for k in FIXED_TRIGGERS},
                'priorities': dict(DEFAULT_TRIGGER_PRIORITY),
            }
            if self._active_id is None:
                self._active_id = bank_id
            self._save()
            return {'id': bank_id, **self._banks[bank_id]}

    def update(self, bank_id: str, name: Optional[str] = None,
               mappings: Optional[dict] = None,
               priorities: Optional[dict] = None) -> Optional[dict]:
        with self._lock:
            bank = self._banks.get(bank_id)
            if bank is None:
                return None
            if name is not None:
                bank['name'] = name
            if mappings is not None:
                for k, v in mappings.items():
                    if k in FIXED_TRIGGERS:
                        bank['mappings'][k] = v
            if priorities is not None:
                for k, v in priorities.items():
                    if k in FIXED_TRIGGERS:
                        try:
                            bank['priorities'][k] = int(v)
                        except (TypeError, ValueError):
                            continue
            self._save()
            return {'id': bank_id, **bank}

    def delete(self, bank_id: str):
        with self._lock:
            self._banks.pop(bank_id, None)
            if self._active_id == bank_id:
                self._active_id = None
            self._save()

    def set_active(self, bank_id: Optional[str]) -> bool:
        with self._lock:
            if bank_id is not None and bank_id not in self._banks:
                return False
            self._active_id = bank_id
            self._save()
            return True

    @property
    def active_id(self) -> Optional[str]:
        with self._lock:
            return self._active_id

    def active_mappings(self) -> dict:
        with self._lock:
            if self._active_id is None:
                return {}
            bank = self._banks.get(self._active_id)
            return dict(bank['mappings']) if bank else {}

    def active_priorities(self) -> dict:
        with self._lock:
            if self._active_id is None:
                return dict(DEFAULT_TRIGGER_PRIORITY)
            bank = self._banks.get(self._active_id)
            if not bank:
                return dict(DEFAULT_TRIGGER_PRIORITY)
            return {**DEFAULT_TRIGGER_PRIORITY, **bank.get('priorities', {})}

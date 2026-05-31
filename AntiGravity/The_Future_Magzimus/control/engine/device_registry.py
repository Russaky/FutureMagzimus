"""Tracks active timelines per device and enforces Device Policies.
Also manages named slot→deviceId mappings for hot-swap support.
"""
import threading
from typing import Callable, Optional


class DeviceRegistry:
    def __init__(self):
        self._lock   = threading.Lock()
        self._active = {}   # device_key → Timeline
        self._queued = {}   # device_key → [Timeline, ...]
        self._slots  = {}   # slot_name → deviceId (int)

    # ─── Timeline scheduling ──────────────────────────────────────────────────

    def run(self, device_key: tuple, timeline, policy: str):
        with self._lock:
            active = self._active.get(device_key)
            if active is None or not active.running:
                self._start(device_key, timeline)
            else:
                if policy == 'INTERRUPT':
                    active.cancel()
                    self._start(device_key, timeline)
                elif policy == 'QUEUE':
                    self._queued.setdefault(device_key, []).append(timeline)
                # IGNORE: drop silently

    def _start(self, device_key: tuple, timeline):
        self._active[device_key] = timeline
        timeline.on_done = lambda: self._on_done(device_key)
        timeline.start()

    def _on_done(self, device_key: tuple):
        with self._lock:
            queue = self._queued.get(device_key, [])
            if queue:
                nxt = queue.pop(0)
                if not queue:
                    del self._queued[device_key]
                self._start(device_key, nxt)
            else:
                self._active.pop(device_key, None)

    def _cancel_device(self, device: str, device_id: int):
        """Cancel all active and queued timelines for a given device+id."""
        key = (device, device_id)
        active = self._active.pop(key, None)
        if active:
            active.cancel()
        self._queued.pop(key, None)

    # ─── Slot management ──────────────────────────────────────────────────────

    def set_slot(self, slot: str, device_id: int):
        """Assign a physical deviceId to a named slot (no cancellation)."""
        with self._lock:
            self._slots[slot] = device_id

    def hotswap(self, slot: str, new_id: int, device_type: Optional[str] = None):
        """Replace the device in a slot. Cancels timelines for the old device.

        device_type: 'staff' | 'relay' | 'pwm' — if provided, cancels typed timelines.
        If None, cancels timelines across all known device types.
        """
        with self._lock:
            old_id = self._slots.get(slot)
            self._slots[slot] = new_id
            if old_id is not None and old_id != new_id:
                types = [device_type] if device_type else ['staff', 'relay', 'pwm']
                for t in types:
                    self._cancel_device(t, old_id)

    def resolve(self, slot: str) -> Optional[int]:
        """Return the deviceId for a slot, or None if undefined."""
        with self._lock:
            return self._slots.get(slot)

    def list_slots(self) -> dict:
        with self._lock:
            return dict(self._slots)

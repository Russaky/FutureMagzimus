"""Tracks active timelines per device and enforces Device Policies.
Also manages named slot→deviceId mappings for hot-swap support.
And manages IDLE state per device: applied when no timeline is running.

Timeline scheduling also supports a numeric priority per run() call (default 1,
used by ordinary Number events). A lower numeric value means a HIGHER priority 
(1 is highest). A higher-priority timeline always interrupts a lower-priority one,
regardless of Policy; a lower-priority timeline can never preempt a higher-priority 
one that is still running. Equal priority falls back to the normal INTERRUPT/QUEUE/IGNORE
policy — this keeps existing (priority=1) behavior unchanged.
"""
from __future__ import annotations
import threading
from typing import Callable, Optional


class DeviceRegistry:
    def __init__(self):
        self._lock   = threading.Lock()
        self._active = {}   # device_key → Timeline
        self._active_priority = {}  # device_key → int
        self._queued = {}   # device_key → [(Timeline, priority), ...]
        self._slots  = {}   # slot_name → deviceId (int)
        self._idles  = {}   # (device, targetId) → cmd dict

    # ─── Timeline scheduling ──────────────────────────────────────────────────

    def run(self, device_key: tuple, timeline, policy: str, priority: int = 1):
        with self._lock:
            active = self._active.get(device_key)
            if active is None or not active.running:
                self._start(device_key, timeline, priority)
                return

            active_priority = self._active_priority.get(device_key, 1)
            if priority < active_priority:
                # Higher-priority (lower number) trigger always wins, regardless of policy.
                active.cancel()
                self._start(device_key, timeline, priority)
            elif priority > active_priority:
                # Lower-priority (higher number) trigger can never preempt a higher one: drop.
                pass
            elif policy == 'INTERRUPT':
                active.cancel()
                self._start(device_key, timeline, priority)
            elif policy == 'QUEUE':
                self._queued.setdefault(device_key, []).append((timeline, priority))
            # IGNORE: drop silently

    def _start(self, device_key: tuple, timeline, priority: int = 1):
        self._active[device_key] = timeline
        self._active_priority[device_key] = priority
        timeline.on_done = lambda: self._on_done(device_key)
        timeline.start()

    def _on_done(self, device_key: tuple):
        with self._lock:
            queue = self._queued.get(device_key, [])
            if queue:
                nxt, nxt_priority = queue.pop(0)
                if not queue:
                    del self._queued[device_key]
                self._start(device_key, nxt, nxt_priority)
            else:
                self._active.pop(device_key, None)
                self._active_priority.pop(device_key, None)

    def _cancel_device(self, device: str, device_id: int):
        """Cancel all active and queued timelines for a given device+id."""
        key = (device, device_id)
        active = self._active.pop(key, None)
        self._active_priority.pop(key, None)
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

    # ─── IDLE state management ────────────────────────────────────────────────

    def set_idle(self, device: str, target_id: int, cmd: dict):
        with self._lock:
            self._idles[(device, target_id)] = cmd

    def get_idle(self, device: str, target_id: int) -> Optional[dict]:
        with self._lock:
            return self._idles.get((device, target_id))

    def apply_all_idles(self, make_sender: Callable):
        """Apply all registered IDLE commands to their devices.
        Called by Engine.show_timer_start() to reset all outputs.
        """
        with self._lock:
            items = list(self._idles.items())
        for (device, target_id), cmd in items:
            try:
                sender = make_sender(device, target_id)
                sender(cmd)
            except Exception:
                pass

    def cancel_all(self):
        """Cancel all active and queued timelines across all devices."""
        with self._lock:
            for tl in list(self._active.values()):
                tl.cancel()
            self._active.clear()
            self._active_priority.clear()
            self._queued.clear()

    def has_active_timeline(self, device: str) -> bool:
        """Check if any active timeline is running for a device type."""
        with self._lock:
            return any(tl.running for (d, _), tl in self._active.items() if d == device)

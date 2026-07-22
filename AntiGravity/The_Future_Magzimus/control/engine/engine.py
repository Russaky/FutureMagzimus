"""Number engine — loads event-driven Number configs and executes Timeline Blocks.

Supports:
  - staff_telemetry triggers (speed, angle, flags: throw/catch/impact/orientation)
  - mic_telemetry triggers (rms, peak, frequency)
  - pedal_event triggers (eventType)
  - ShowTimer: resets all timelines and fires a countdown
  - Accumulator: accumulates pulses 0-100, fires scored/climax events, supports decay
  - IDLE state per device: applied when no timeline is running or ShowTimer resets
"""
from __future__ import annotations
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

import yaml

from device_registry import DeviceRegistry
from timeline import Timeline
from bank_manager import BankStore, FIXED_TRIGGERS, eval_fixed_trigger

DEFAULT_BANKS_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'banks', 'banks.json')
STAFF_WATCHDOG_TIMEOUT_SEC = 3.0


class ShowTimer:
    """Counts down a duration, resets all devices to IDLE at start, fires 'done' on finish."""

    def __init__(self, duration_sec: float, on_tick: Callable[[float], None] | None,
                 on_done: Callable[[], None] | None):
        self._duration  = duration_sec
        self._on_tick   = on_tick
        self._on_done   = on_done
        self._thread: threading.Thread | None = None
        self._running   = False
        self._remaining = duration_sec

    @property
    def running(self) -> bool:
        return self._running

    @property
    def remaining(self) -> float:
        return self._remaining

    def start(self):
        if self._running:
            self.stop()
        self._remaining = self._duration
        self._running   = True
        self._thread    = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _run(self):
        start = time.monotonic()
        while self._running:
            elapsed = time.monotonic() - start
            self._remaining = max(0.0, self._duration - elapsed)
            if self._on_tick:
                self._on_tick(self._remaining)
            if self._remaining <= 0:
                self._running = False
                if self._on_done:
                    self._on_done()
                break
            time.sleep(0.1)


class ConnectionWatchdog:
    """Fires `on_timeout` once if `touch()` isn't called for `timeout_sec`.

    Used to detect a dead StaffTelemetry stream (radio loss, staff powered
    off) and fall back to IDLE instead of leaving the last effect running
    forever. Re-arms automatically on the next touch().
    """

    def __init__(self, timeout_sec: float, on_timeout: Callable[[], None] | None,
                 poll_interval: float = 0.25):
        self._timeout_sec   = timeout_sec
        self._on_timeout    = on_timeout
        self._poll_interval = poll_interval
        self._lock          = threading.Lock()
        self._last_seen     = time.monotonic()
        self._timed_out     = False
        self._thread        = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def touch(self):
        with self._lock:
            self._last_seen = time.monotonic()
            self._timed_out = False

    def _run(self):
        while True:
            time.sleep(self._poll_interval)
            with self._lock:
                if self._timed_out:
                    continue
                elapsed = time.monotonic() - self._last_seen
                if elapsed < self._timeout_sec:
                    continue
                self._timed_out = True
            if self._on_timeout:
                self._on_timeout()


class Accumulator:
    """Pulse-based progress accumulator (0–100). Supports decay and climax event."""

    def __init__(self, decay_rate: float = 0.0,
                 on_scored: Callable[[float], None] | None = None,
                 on_climax: Callable[[], None] | None = None):
        self._value      = 0.0
        self._decay_rate = decay_rate   # % per second
        self._on_scored  = on_scored
        self._on_climax  = on_climax
        self._climaxed   = False
        self._lock       = threading.Lock()
        self._last_decay = time.monotonic()
        self._thread     = threading.Thread(target=self._decay_loop, daemon=True)
        self._thread.start()

    @property
    def value(self) -> float:
        return self._value

    def pulse(self, amount: float = 1.0):
        with self._lock:
            self._value = min(100.0, self._value + amount)
            if self._on_scored:
                self._on_scored(self._value)
            if self._value >= 100.0 and not self._climaxed:
                self._climaxed = True
                if self._on_climax:
                    self._on_climax()

    def reset(self):
        with self._lock:
            self._value    = 0.0
            self._climaxed = False

    def _decay_loop(self):
        while True:
            time.sleep(0.1)
            if self._decay_rate <= 0:
                continue
            now = time.monotonic()
            dt  = now - self._last_decay
            self._last_decay = now
            with self._lock:
                if self._value > 0:
                    self._value = max(0.0, self._value - self._decay_rate * dt)
                    if self._on_scored:
                        self._on_scored(self._value)
                    if self._value < 100.0:
                        self._climaxed = False


class Engine:
    def __init__(self,
                 send_staff:    Callable,
                 send_relay:    Callable,
                 send_pwm:      Callable,
                 send_progress: Callable | None = None,
                 send_dmx:      Callable | None = None,
                 send_effect:   Callable | None = None,
                 resolve_effect: Callable[[str], dict | None] | None = None,
                 banks_path:    str | None = None):
        self._send_staff    = send_staff
        self._send_relay    = send_relay
        self._send_pwm      = send_pwm
        self._send_progress = send_progress
        self._send_dmx      = send_dmx
        self._send_effect   = send_effect       # generic FastLED EffectCommand sender (staff only)
        self._resolve_effect = resolve_effect   # effect_id -> saved effect dict (control.engine.effects_library)
        self._registry      = DeviceRegistry()
        self._numbers       = []
        self._show_timer:   ShowTimer | None  = None
        self._accumulator:  Accumulator | None = None
        self._on_event:     Callable[[str, dict], None] | None = None
        self._trigger_state: dict[str, bool] = {}  # event id → last condition state (edge detection)
        self.reactive_lights_enabled = False
        self._bank_store    = BankStore(banks_path or DEFAULT_BANKS_PATH)
        self._staff_watchdog = ConnectionWatchdog(
            STAFF_WATCHDOG_TIMEOUT_SEC, on_timeout=self._on_staff_watchdog_timeout)

    # ─── Configuration ────────────────────────────────────────────────────────

    def set_event_callback(self, cb: Callable[[str, dict], None]):
        """Receive engine events: ('showtimer_tick', {'remaining': …}), ('scored', …), etc."""
        self._on_event = cb

    def load(self, path: str):
        p = Path(path)
        with open(p) as f:
            data = yaml.safe_load(f) if p.suffix in ('.yaml', '.yml') else json.load(f)
        self._numbers = data if isinstance(data, list) else [data]
        self._trigger_state.clear()
        # Propagate IDLE definitions to registry
        for number in self._numbers:
            for idle_def in number.get('idle_states', []):
                device = idle_def.get('device')
                target = idle_def.get('targetId', 0xFFFF)
                cmd    = idle_def.get('cmd', {})
                if device:
                    self._registry.set_idle(device, target, cmd)

    # ─── ShowTimer ────────────────────────────────────────────────────────────

    def show_timer_start(self, duration_sec: float):
        if self._show_timer and self._show_timer.running:
            self._show_timer.stop()
        self._registry.cancel_all()
        self._registry.apply_all_idles(self._make_sender)
        self._show_timer = ShowTimer(
            duration_sec,
            on_tick=lambda r: self._emit('showtimer_tick', {'remaining': r}),
            on_done=lambda: self._on_show_timer_done(),
        )
        self._show_timer.start()

    def show_timer_stop(self):
        if self._show_timer:
            self._show_timer.stop()

    def _on_show_timer_done(self):
        self._emit('showtimer_done', {})
        if self._accumulator:
            self._accumulator.reset()

    # ─── Accumulator ─────────────────────────────────────────────────────────

    def accumulator_configure(self, decay_rate: float = 0.0):
        self._accumulator = Accumulator(
            decay_rate=decay_rate,
            on_scored=lambda v: self._emit('scored', {'value': v}),
            on_climax=lambda: self._emit('climax', {}),
        )

    def accumulator_pulse(self, amount: float = 1.0):
        if self._accumulator:
            self._accumulator.pulse(amount)

    def accumulator_reset(self):
        if self._accumulator:
            self._accumulator.reset()

    @property
    def accumulator_value(self) -> float:
        return self._accumulator.value if self._accumulator else 0.0

    # ─── Telemetry ingress ────────────────────────────────────────────────────

    def on_telemetry(self, data: dict):
        """Route incoming staff telemetry to matching event triggers."""
        self._staff_watchdog.touch()
        for number in self._numbers:
            for event in number.get('events', []):
                self._dispatch_trigger(event, self._check_trigger(event['trigger'], data))

        # Active Bank routing: fixed motion triggers → mapped network commands
        self._dispatch_bank_triggers(data)

        # Real-time reactive mapping to stage lights
        self._apply_reactive_lights(data)

    def on_mic_telemetry(self, data: dict):
        """Route incoming microphone telemetry."""
        enriched = {**data, '_type': 'mic_telemetry'}
        for number in self._numbers:
            for event in number.get('events', []):
                self._dispatch_trigger(event, self._check_trigger(event['trigger'], enriched))

    def on_pedal_event(self, data: dict):
        """Route incoming pedal event."""
        enriched = {**data, '_type': 'pedal_event'}
        for number in self._numbers:
            for event in number.get('events', []):
                self._dispatch_trigger(event, self._check_trigger(event['trigger'], enriched))

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _dispatch_trigger(self, event: dict, matched: bool):
        """Fire on the rising edge only (False→True), so level-style conditions
        evaluated on a telemetry stream (e.g. `20 <= angle <= 340`) trigger once
        per state change instead of restarting the timeline on every packet."""
        event_id  = event.get('id', id(event))
        was_armed = self._trigger_state.get(event_id, False)
        self._trigger_state[event_id] = matched
        if matched and not was_armed:
            self._fire_event(event)

    def _dispatch_bank_triggers(self, data: dict):
        """Evaluate the 6 fixed Bank triggers (edge-detected) against the Active
        Bank's mapping and fire the mapped network command, if any."""
        for key in FIXED_TRIGGERS:
            matched   = eval_fixed_trigger(key, data)
            event_id  = f'__bank__:{key}'
            was_armed = self._trigger_state.get(event_id, False)
            self._trigger_state[event_id] = matched
            if matched and not was_armed:
                self._fire_bank_action(key)

    def _fire_bank_action(self, trigger_key: str):
        timelines = self._bank_store.active_mappings().get(trigger_key)
        if not timelines:
            return
        priority = self._bank_store.active_priorities().get(trigger_key, 1)
        self._fire_event({'id': f'bank:{trigger_key}', 'timelines': timelines}, priority=priority)
        self._emit('bank_triggered', {'bank': self._bank_store.active_id, 'trigger': trigger_key})

    def _on_staff_watchdog_timeout(self):
        """3s without StaffTelemetry: stop chasing stale motion, fall back to IDLE."""
        self._registry.cancel_all()
        self._registry.apply_all_idles(self._make_sender)
        self._emit('watchdog_timeout', {'source': 'staff_telemetry', 'timeoutSec': STAFF_WATCHDOG_TIMEOUT_SEC})

    def _emit(self, event_name: str, data: dict):
        if self._on_event:
            self._on_event(event_name, data)

    # String constants injected into eval context so users can write
    # `orientation == vertical` instead of `orientation == 'vertical'`
    _EVAL_CONSTS = {
        'vertical': 'vertical', 'horizontal': 'horizontal', 'inverted': 'inverted',
        'short': 'short', 'long': 'long', 'double': 'double', 'triple': 'triple',
        'press': 'press', 'release': 'release',
    }

    def _check_trigger(self, trigger: dict, data: dict) -> bool:
        ttype = trigger.get('type', '')
        ctx   = {**self._EVAL_CONSTS, **data}

        if ttype == 'staff_telemetry':
            if data.get('_type') not in (None, 'staff_telemetry'):
                return False
            try:
                return bool(eval(trigger['condition'], {}, ctx))  # noqa: S307
            except Exception:
                return False

        if ttype == 'mic_telemetry':
            if data.get('_type') != 'mic_telemetry':
                return False
            try:
                return bool(eval(trigger['condition'], {}, ctx))  # noqa: S307
            except Exception:
                return False

        if ttype == 'pedal_event':
            if data.get('_type') != 'pedal_event':
                return False
            try:
                return bool(eval(trigger['condition'], {}, ctx))  # noqa: S307
            except Exception:
                # Fallback: legacy eventType field
                expected = trigger.get('eventType')
                return expected is None or data.get('eventType') == expected

        return False

    def _fire_event(self, event: dict, priority: int = 1):
        for tl_def in event.get('timelines', []):
            device = tl_def['device']
            policy = tl_def.get('policy', 'IGNORE')
            steps  = tl_def['steps']

            slot = tl_def.get('targetSlot')
            if slot is not None:
                target = self._registry.resolve(slot)
                if target is None:
                    continue
            else:
                target = tl_def.get('targetId', 0xFFFF)

            key = (device, target)
            tl  = Timeline(steps, self._make_sender(device, target))
            idle_cmd = self._registry.get_idle(device, target)
            if idle_cmd is not None:
                tl.on_done_callback = lambda d=device, t=target, c=idle_cmd: self._send_idle(d, t, c)
            self._registry.run(key, tl, policy, priority)

    def _send_idle(self, device: str, target: int, cmd: dict):
        self._execute_step(device, target, cmd)

    def _make_sender(self, device: str, target: int) -> Callable[[dict], None]:
        def send(step: dict):
            self._execute_step(device, target, step)
        return send

    def _execute_step(self, device: str, target: int, step: dict):
        cmd = step.get('cmd', '')

        # A saved Effects Lab preset used as a Bank/Number action step — the
        # step only carries {cmd:'EFFECT', effectId}; device/target/policy
        # still come from the block, exactly like any other step. This is
        # how effects get attached to a trigger "as a command" without the
        # effect itself ever needing to know which physical unit it targets.
        if cmd == 'EFFECT':
            effect = self._resolve_effect(step['effectId']) if self._resolve_effect else None
            if effect is None:
                return
            self._dispatch_effect_preset(effect, target)
            return

        if device == 'staff':
            if cmd == 'LED_SOLID':
                self._send_staff(target, 1, step.get('r', 0), step.get('g', 0),
                                 step.get('b', 0), step.get('brightness', 150))
            elif cmd == 'LED_OFF':
                self._send_staff(target, 0, 0, 0, 0, 0)
            elif cmd == 'LED_SPARKLE':
                self._send_staff(target, 2, step.get('r', 255), step.get('g', 255),
                                 step.get('b', 255), step.get('density', 128))
            elif cmd == 'LED_FLAME':
                self._send_staff(target, 3, 0, 0, 0, 0)
            elif cmd == 'LED_RAINBOW':
                self._send_staff(target, 4, 0, 0, 0, 0)
            elif cmd == 'LED_VERTICAL':
                self._send_staff(target, 7, 0, 0, 0, 0)
        elif device == 'relay':
            if cmd == 'RELAY_ON':
                self._send_relay(target, 1, step.get('durationMs', 0))
            elif cmd == 'RELAY_OFF':
                self._send_relay(target, 0, 0)
        elif device == 'pwm':
            if cmd == 'PWM_SET':
                self._send_pwm(target, step.get('w', 0), step.get('r', 0),
                               step.get('g', 0), step.get('b', 0), step.get('fadeMs', 0))
        elif device == 'progressbar':
            if self._send_progress and cmd == 'PROGRESS_SET':
                self._send_progress(target, step.get('mode', 0), step.get('value', 0),
                                    step.get('r', 0), step.get('g', 0), step.get('b', 0),
                                    step.get('fadeMs', 0))
        elif device == 'dmx':
            if self._send_dmx and cmd == 'DMX_SET':
                self._send_dmx(target, step.get('w', 0), step.get('r', 0),
                               step.get('g', 0), step.get('b', 0))

    def _dispatch_effect_preset(self, effect: dict, target: int):
        """Send a saved Effects Lab preset through the right sender — mirrors
        control/server/app.py's _dispatch_effect(), but device-agnostic (only
        talks through the injected send_* callables, never proto/_tx directly)."""
        device_type = effect.get('deviceType', 'staff')
        if device_type == 'staff':
            if self._send_effect:
                self._send_effect(target, effect.get('templateId', 0), effect.get('paletteId', 0),
                                  effect.get('speed', 128), effect.get('intensity', 200),
                                  effect.get('param1', 0), effect.get('param2', 0),
                                  effect.get('reactiveSource', 0), effect.get('reactiveParam', 0),
                                  effect.get('colorMode', 0),
                                  effect.get('pr', 0), effect.get('pg', 0), effect.get('pb', 0),
                                  effect.get('sr', 0), effect.get('sg', 0), effect.get('sb', 0))
        elif device_type == 'dmx':
            self._send_dmx(target, effect.get('w', 0), effect.get('r', 0),
                          effect.get('g', 0), effect.get('b', 0))
        elif device_type == 'pwm':
            self._send_pwm(target, effect.get('w', 0), effect.get('r', 0),
                          effect.get('g', 0), effect.get('b', 0), effect.get('fadeMs', 0))
        elif device_type == 'progressbar' and self._send_progress:
            self._send_progress(target, effect.get('mode', 1), effect.get('value', 0),
                               effect.get('r', 0), effect.get('g', 0), effect.get('b', 0),
                               effect.get('fadeMs', 0))

    def _apply_reactive_lights(self, data: dict):
        if not getattr(self, 'reactive_lights_enabled', False):
            return

        # If any active timeline is running on pwm devices, let it have control
        if self._registry.has_active_timeline('pwm'):
            return

        speed = data.get('speed', 0.0)
        angle = data.get('angle', 0.0)
        
        # Throw, catch and impact flags (from bitmask or helper bool properties)
        throw = data.get('throw', False)
        catch = data.get('catch', False)
        impact = data.get('impact', False)

        w, r, g, b = 0, 0, 0, 0
        fade_ms = 100

        if impact:
            w, r, g, b = 255, 255, 255, 255
            fade_ms = 0
            self._send_pwm(0xFF, w, r, g, b, fade_ms)
            return
        elif throw:
            w, r, g, b = 0, 0, 100, 255
            fade_ms = 50
            self._send_pwm(0xFF, w, r, g, b, fade_ms)
            return
        elif catch:
            w, r, g, b = 100, 255, 120, 0
            fade_ms = 50
            self._send_pwm(0xFF, w, r, g, b, fade_ms)
            return

        # Normal rotation mapping
        if speed < 3.0:
            # Slow rotation / idle: Warm white default
            w, r, g, b = 80, 30, 10, 0
            fade_ms = 200
            self._send_pwm(0xFF, w, r, g, b, fade_ms)
        else:
            # Fast spinning: corner chase based on tilt angle
            import math
            ang_norm = float(angle) % 360.0
            
            # Corner angles: C1=0/360, C2=90, C3=180, C4=270
            # Base color: Flame orange
            base_r, base_g, base_b = 255, 80, 0
            speed_factor = min(1.0, (speed - 3.0) / 10.0)
            
            for cid, center_deg in [(1, 0), (2, 90), (3, 180), (4, 270)]:
                diff = math.radians(ang_norm - center_deg)
                weight = max(0.0, math.cos(diff))
                weight = weight ** 2 # sharper focus
                
                c_r = int(base_r * speed_factor * weight)
                c_g = int(base_g * speed_factor * weight)
                c_b = int(base_b * speed_factor * weight)
                
                self._send_pwm(cid, 0, c_r, c_g, c_b, 80)

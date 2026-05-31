"""Number engine — loads event-driven Number configs and executes Timeline Blocks."""
import json
from pathlib import Path
from typing import Callable

import yaml

from device_registry import DeviceRegistry
from timeline import Timeline


class Engine:
    def __init__(self,
                 send_staff: Callable,
                 send_relay: Callable,
                 send_pwm:   Callable):
        self._send_staff = send_staff
        self._send_relay = send_relay
        self._send_pwm   = send_pwm
        self._registry   = DeviceRegistry()
        self._numbers    = []

    def load(self, path: str):
        p = Path(path)
        with open(p) as f:
            data = yaml.safe_load(f) if p.suffix in ('.yaml', '.yml') else json.load(f)
        self._numbers = data if isinstance(data, list) else [data]

    def on_telemetry(self, data: dict):
        for number in self._numbers:
            for event in number.get('events', []):
                if self._check_trigger(event['trigger'], data):
                    self._fire_event(event)

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _check_trigger(self, trigger: dict, data: dict) -> bool:
        if trigger.get('type') != 'staff_telemetry':
            return False
        # Evaluate condition string against telemetry fields.
        # Numbers are authored locally — eval is intentional here.
        try:
            return bool(eval(trigger['condition'], {}, data))  # noqa: S307
        except Exception:
            return False

    def _fire_event(self, event: dict):
        for tl_def in event.get('timelines', []):
            device = tl_def['device']
            policy = tl_def.get('policy', 'IGNORE')
            steps  = tl_def['steps']

            slot = tl_def.get('targetSlot')
            if slot is not None:
                target = self._registry.resolve(slot)
                if target is None:
                    continue   # slot not assigned yet — skip
            else:
                target = tl_def.get('targetId', 0xFFFF)

            key = (device, target)
            tl  = Timeline(steps, self._make_sender(device, target))
            self._registry.run(key, tl, policy)

    def _make_sender(self, device: str, target: int) -> Callable[[dict], None]:
        def send(step: dict):
            cmd = step.get('cmd', '')
            if device == 'staff':
                if cmd == 'LED_SOLID':
                    self._send_staff(target, 1,
                                     step.get('r', 0), step.get('g', 0),
                                     step.get('b', 0), step.get('brightness', 150))
                elif cmd == 'LED_OFF':
                    self._send_staff(target, 0, 0, 0, 0, 0)
            elif device == 'relay':
                if cmd == 'RELAY_ON':
                    self._send_relay(target, 1, step.get('durationMs', 0))
                elif cmd == 'RELAY_OFF':
                    self._send_relay(target, 0, 0)
            elif device == 'pwm':
                if cmd == 'PWM_SET':
                    self._send_pwm(target,
                                   step.get('w', 0), step.get('r', 0),
                                   step.get('g', 0), step.get('b', 0),
                                   step.get('fadeMs', 0))
        return send

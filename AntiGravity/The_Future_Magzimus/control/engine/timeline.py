"""Executes a sequence of timed steps on a single device."""
from __future__ import annotations
import threading
import time
from typing import Callable


class Timeline:
    def __init__(self, steps: list, send_fn: Callable[[dict], None]):
        self._steps  = steps
        self._send   = send_fn
        self._timers: list[threading.Timer] = []
        self.running = False
        self.on_done: Callable | None = None

    def start(self):
        self.running  = True
        t_origin      = time.monotonic()

        for step in self._steps:
            delay = max(0.0, step['t'] - (time.monotonic() - t_origin))
            t = threading.Timer(delay, self._fire, args=[step])
            t.daemon = True
            t.start()
            self._timers.append(t)

        end = self._steps[-1]['t'] if self._steps else 0.0
        done_t = threading.Timer(end + 0.05, self._done)
        done_t.daemon = True
        done_t.start()
        self._timers.append(done_t)

    def cancel(self):
        self.running = False
        for t in self._timers:
            t.cancel()

    def _fire(self, step: dict):
        if self.running:
            self._send(step)

    def _done(self):
        self.running = False
        if self.on_done:
            self.on_done()

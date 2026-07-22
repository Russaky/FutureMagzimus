#!/usr/bin/env python3
"""
Engine edge-case stress test — no hardware required.
Tests trigger evaluation, policy enforcement, timer, accumulator.
"""
import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../control/engine'))

from engine import Engine, ShowTimer, Accumulator

PASS = "\033[32m  ✓ \033[0m"
FAIL = "\033[31m  ✗ \033[0m"
errors = []

def check(label, result, expected=True):
    ok = bool(result) == bool(expected)
    sym = PASS if ok else FAIL
    print(f"{sym} {label}")
    if not ok:
        errors.append(label)
    return ok

def make_engine():
    fired = []
    def send_staff(target, mode, r, g, b, x):
        fired.append(('staff', target, mode, r, g, b, x))
    def send_relay(target, on, dur):
        fired.append(('relay', target, on, dur))
    def send_pwm(target, w, r, g, b, fade):
        fired.append(('pwm', target, w, r, g, b, fade))
    e = Engine(send_staff, send_relay, send_pwm)
    return e, fired

# ─── Section 1: String-condition triggers ─────────────────────────────────────
print("\n=== 1. String-condition triggers ===")

NUMBER_ORIENT = [{
    "events": [
        {
            "trigger": {"type": "staff_telemetry", "condition": "orientation == vertical"},
            "timelines": [{"device": "staff", "targetId": 1, "policy": "INTERRUPT",
                           "steps": [{"t": 0, "cmd": "LED_SOLID", "r": 255, "g": 0, "b": 0, "brightness": 150}]}]
        },
        {
            "trigger": {"type": "staff_telemetry", "condition": "orientation == horizontal"},
            "timelines": [{"device": "staff", "targetId": 1, "policy": "INTERRUPT",
                           "steps": [{"t": 0, "cmd": "LED_SOLID", "r": 0, "g": 255, "b": 0, "brightness": 150}]}]
        }
    ]
}]

import tempfile, json
def load_number(e, number_def):
    with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
        json.dump(number_def, f)
        fname = f.name
    e.load(fname)
    os.unlink(fname)

e, fired = make_engine()
load_number(e, NUMBER_ORIENT)

fired.clear()
e.on_telemetry({'orientation': 'vertical', 'speed': 1.0})
time.sleep(0.05)
check("orientation==vertical fires", len(fired) > 0)

fired.clear()
e.on_telemetry({'orientation': 'horizontal', 'speed': 1.0})
time.sleep(0.05)
check("orientation==horizontal fires", len(fired) > 0)

fired.clear()
e.on_telemetry({'orientation': 'inverted', 'speed': 1.0})
time.sleep(0.05)
check("orientation==inverted no fire (no trigger for it)", len(fired) == 0)

# ─── Section 2: Numeric triggers ──────────────────────────────────────────────
print("\n=== 2. Numeric triggers ===")

NUMBER_SPEED = [{
    "events": [{
        "trigger": {"type": "staff_telemetry", "condition": "speed > 2.0"},
        "timelines": [{"device": "relay", "targetId": 2, "policy": "IGNORE",
                       "steps": [{"t": 0, "cmd": "RELAY_ON", "durationMs": 500}]}]
    }]
}]

e2, fired2 = make_engine()
load_number(e2, NUMBER_SPEED)

fired2.clear()
e2.on_telemetry({'speed': 3.5})
time.sleep(0.05)
check("speed>2.0 fires at 3.5", len(fired2) > 0)

fired2.clear()
e2.on_telemetry({'speed': 1.0})
time.sleep(0.05)
check("speed>2.0 no fire at 1.0", len(fired2) == 0)

# ─── Section 3: Pedal event eval ──────────────────────────────────────────────
print("\n=== 3. Pedal event triggers ===")

NUMBER_PEDAL = [{
    "events": [
        {
            "trigger": {"type": "pedal_event", "condition": "eventType == long"},
            "timelines": [{"device": "relay", "targetId": 3, "policy": "INTERRUPT",
                           "steps": [{"t": 0, "cmd": "RELAY_ON", "durationMs": 1000}]}]
        },
        {
            "trigger": {"type": "pedal_event", "condition": "eventType == short"},
            "timelines": [{"device": "pwm", "targetId": 4, "policy": "INTERRUPT",
                           "steps": [{"t": 0, "cmd": "PWM_SET", "w": 255, "r": 0, "g": 0, "b": 0, "fadeMs": 0}]}]
        }
    ]
}]

e3, fired3 = make_engine()
load_number(e3, NUMBER_PEDAL)

fired3.clear()
e3.on_pedal_event({'eventType': 'long'})
time.sleep(0.05)
check("pedal long fires relay", any(x[0] == 'relay' for x in fired3))

fired3.clear()
e3.on_pedal_event({'eventType': 'short'})
time.sleep(0.05)
check("pedal short fires pwm", any(x[0] == 'pwm' for x in fired3))

fired3.clear()
e3.on_pedal_event({'eventType': 'double'})
time.sleep(0.05)
check("pedal double no fire (no trigger)", len(fired3) == 0)

# ─── Section 4: Mic telemetry triggers ────────────────────────────────────────
print("\n=== 4. Mic telemetry triggers ===")

NUMBER_MIC = [{
    "events": [{
        "trigger": {"type": "mic_telemetry", "condition": "frequency > 400"},
        "timelines": [{"device": "pwm", "targetId": 5, "policy": "IGNORE",
                       "steps": [{"t": 0, "cmd": "PWM_SET", "w": 0, "r": 255, "g": 0, "b": 0, "fadeMs": 200}]}]
    }]
}]

e4, fired4 = make_engine()
load_number(e4, NUMBER_MIC)

fired4.clear()
e4.on_mic_telemetry({'rms': 0.5, 'peak': 0.8, 'frequency': 440})
time.sleep(0.05)
check("mic frequency 440Hz fires", len(fired4) > 0)

fired4.clear()
e4.on_mic_telemetry({'rms': 0.5, 'peak': 0.8, 'frequency': 300})
time.sleep(0.05)
check("mic frequency 300Hz no fire", len(fired4) == 0)

# Mic should not fire on staff telemetry
fired4.clear()
e4.on_telemetry({'frequency': 440})
time.sleep(0.05)
check("mic trigger does not fire on staff telemetry", len(fired4) == 0)

# ─── Section 5: INTERRUPT / QUEUE / IGNORE policies ──────────────────────────
print("\n=== 5. Device policies ===")

from device_registry import DeviceRegistry
from timeline import Timeline

registry = DeviceRegistry()
log = []

def make_tl(label, dur):
    def sender(step):
        log.append((label, step.get('cmd', '?')))
    steps = [{"t": 0, "cmd": "START"}, {"t": dur, "cmd": "END"}]
    tl = Timeline(steps, sender)
    return tl

# INTERRUPT: second timeline cancels first
tl1 = make_tl("A", 2.0)
tl2 = make_tl("B", 0.1)
registry.run(('staff', 10), tl1, 'INTERRUPT')
time.sleep(0.01)
registry.run(('staff', 10), tl2, 'INTERRUPT')
time.sleep(0.15)
b_ran = any(l[0] == 'B' for l in log)
a_cancelled = not any(l == ('A', 'END') for l in log)
check("INTERRUPT: second TL runs", b_ran)
check("INTERRUPT: first TL cancelled (no END)", a_cancelled)

# QUEUE: second waits for first
registry2 = DeviceRegistry()
log2 = []
tl3 = make_tl_log2 = []
tl3 = Timeline([{"t": 0, "cmd": "C_START"}, {"t": 0.1, "cmd": "C_END"}], lambda s: log2.append(('C', s.get('cmd',''))))
tl4 = Timeline([{"t": 0, "cmd": "D_START"}, {"t": 0.05, "cmd": "D_END"}], lambda s: log2.append(('D', s.get('cmd',''))))
registry2.run(('relay', 20), tl3, 'QUEUE')
registry2.run(('relay', 20), tl4, 'QUEUE')
time.sleep(0.3)
c_done = ('C', 'C_END') in log2
d_done = ('D', 'D_END') in log2
c_before_d = log2.index(('C', 'C_END')) < log2.index(('D', 'D_START')) if c_done and d_done else False
check("QUEUE: both timelines run", c_done and d_done)
check("QUEUE: C finishes before D starts", c_before_d)

# IGNORE: second is dropped if first is running
registry3 = DeviceRegistry()
log3 = []
tl5 = Timeline([{"t": 0, "cmd": "E_START"}, {"t": 0.3, "cmd": "E_END"}], lambda s: log3.append(('E', s.get('cmd',''))))
tl6 = Timeline([{"t": 0, "cmd": "F_START"}], lambda s: log3.append(('F', s.get('cmd',''))))
registry3.run(('pwm', 30), tl5, 'IGNORE')
time.sleep(0.01)
registry3.run(('pwm', 30), tl6, 'IGNORE')
time.sleep(0.05)
f_ran = any(l[0] == 'F' for l in log3)
check("IGNORE: second TL is dropped", not f_ran)

# ─── Section 6: ShowTimer ─────────────────────────────────────────────────────
print("\n=== 6. ShowTimer ===")

tick_count = [0]
done_flag  = [False]
timer = ShowTimer(0.3,
    on_tick=lambda r: tick_count.__setitem__(0, tick_count[0]+1),
    on_done=lambda: done_flag.__setitem__(0, True))
timer.start()
check("ShowTimer starts running", timer.running)
time.sleep(0.5)
check("ShowTimer finishes", done_flag[0])
check("ShowTimer ticked multiple times", tick_count[0] >= 2)
check("ShowTimer remaining == 0", timer.remaining == 0.0)

# Double start should not deadlock
timer2 = ShowTimer(0.2, None, None)
timer2.start()
timer2.start()  # restart while running
time.sleep(0.4)
check("ShowTimer double-start no deadlock", True)

# ─── Section 7: Accumulator ───────────────────────────────────────────────────
print("\n=== 7. Accumulator ===")

scored_vals = []
climax_flag = [False]
acc = Accumulator(
    decay_rate=50.0,
    on_scored=lambda v: scored_vals.append(v),
    on_climax=lambda: climax_flag.__setitem__(0, True))

acc.pulse(60.0)
check("Accumulator pulse to 60", acc.value == 60.0)
acc.pulse(50.0)  # should clamp at 100
check("Accumulator clamps at 100", acc.value == 100.0)
check("Accumulator fires climax at 100", climax_flag[0])

time.sleep(1.0)
check("Accumulator decays ~50%/s (value < 70 after 1s)", acc.value < 70.0)

acc.reset()
check("Accumulator resets to 0", acc.value == 0.0)

# ─── Section 8: Malformed inputs ──────────────────────────────────────────────
print("\n=== 8. Malformed inputs ===")

e5, fired5 = make_engine()

# Trigger with no condition key — should not crash
e5._numbers = [{"events": [{"trigger": {"type": "staff_telemetry"}, "timelines": []}]}]
try:
    e5.on_telemetry({'speed': 1.0})
    check("Missing condition key: no crash", True)
except Exception as ex:
    check("Missing condition key: no crash", False)

# Trigger with bad condition syntax
e5._numbers = [{"events": [{"trigger": {"type": "staff_telemetry", "condition": "((("}, "timelines": []}]}]
try:
    e5.on_telemetry({'speed': 1.0})
    check("Bad syntax condition: no crash", True)
except Exception:
    check("Bad syntax condition: no crash", False)

# Empty events list
e5._numbers = [{"events": []}]
try:
    e5.on_telemetry({'speed': 1.0})
    check("Empty events list: no crash", True)
except Exception:
    check("Empty events list: no crash", False)

# Load malformed JSON
try:
    with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
        f.write("{bad json{{")
        bad_fname = f.name
    e5.load(bad_fname)
    os.unlink(bad_fname)
    check("Malformed JSON: no crash", False)
except Exception:
    os.unlink(bad_fname) if os.path.exists(bad_fname) else None
    check("Malformed JSON raises exception (expected)", True)

# ─── Section 9: Cross-type isolation ──────────────────────────────────────────
print("\n=== 9. Cross-type isolation ===")

NUMBER_ISOLATED = [{
    "events": [
        {
            "trigger": {"type": "staff_telemetry", "condition": "speed > 1"},
            "timelines": [{"device": "staff", "targetId": 1, "policy": "IGNORE",
                           "steps": [{"t": 0, "cmd": "LED_SOLID", "r": 255, "g": 0, "b": 0, "brightness": 150}]}]
        },
        {
            "trigger": {"type": "mic_telemetry", "condition": "rms > 0.5"},
            "timelines": [{"device": "relay", "targetId": 2, "policy": "IGNORE",
                           "steps": [{"t": 0, "cmd": "RELAY_ON", "durationMs": 100}]}]
        }
    ]
}]

e6, fired6 = make_engine()
load_number(e6, NUMBER_ISOLATED)

# mic telemetry should not trigger staff trigger
fired6.clear()
e6.on_mic_telemetry({'rms': 0.9, 'peak': 1.0, 'frequency': 500})
time.sleep(0.05)
check("Mic telemetry does not fire staff_telemetry trigger", not any(x[0]=='staff' for x in fired6))
check("Mic telemetry fires its own trigger", any(x[0]=='relay' for x in fired6))

# staff telemetry should not trigger mic trigger
fired6.clear()
e6.on_telemetry({'speed': 5.0})
time.sleep(0.05)
check("Staff telemetry does not fire mic_telemetry trigger", not any(x[0]=='relay' for x in fired6))
check("Staff telemetry fires its own trigger", any(x[0]=='staff' for x in fired6))

# ─── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*40}")
if errors:
    print(f"\033[31m{len(errors)} errors:\033[0m")
    for e in errors:
        print(f"  ✗  {e}")
else:
    print("\033[32mAll tests passed.\033[0m")
sys.exit(len(errors))

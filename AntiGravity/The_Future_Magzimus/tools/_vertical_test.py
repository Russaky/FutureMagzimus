"""Ad-hoc live test for the Staff Vertical Green/Blue number.
Connects to the Hub over serial, calibrates the Staff via ESP-NOW,
then streams live telemetry (angle/speed/orientation) for manual verification.
"""
import sys, os, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'control', 'server'))
import protocol as proto
from serial_bridge import SerialBridge

HUB_PORT = sys.argv[1] if len(sys.argv) > 1 else '/dev/cu.usbmodem143201'
BAUD     = 115200

last = {}

def on_telem(d):
    last[d.get('deviceId')] = d

def on_ident(d):
    print(f"[identity] {d}", flush=True)

bridge = SerialBridge(HUB_PORT, BAUD, on_telem, on_ident, lambda d: None, lambda d: None, lambda d: None)
bridge.start()
print(f"[serial] connected to {HUB_PORT}", flush=True)
time.sleep(1.0)

print("[calibrate] sending CMD_CALIBRATE (broadcast 0xFFFF) — keep the staff still...", flush=True)
bridge.send(proto.pack_staff_command(0xFFFF, 6, 0, 0, 0, 0))
time.sleep(3.0)
print("[calibrate] done — starting telemetry stream\n", flush=True)

t0 = time.time()
while True:
    time.sleep(0.2)
    for did, d in sorted(last.items()):
        ang = d.get('angle', 0.0)
        verticalish = abs(ang) <= 20.0
        print(f"  t={time.time()-t0:6.1f}s  id={did:04X}  angle={ang:7.2f}°  "
              f"speed={d.get('speed',0):6.3f}  orientation={d.get('orientation','?'):10s}  "
              f"{'<<< VERTICAL-UP (green zone)' if verticalish else ''}", flush=True)

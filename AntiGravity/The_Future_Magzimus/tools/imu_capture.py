"""Live IMU capture for Roll-vs-Spin axis diagnosis.

Connects directly to the Hub's serial port (bypassing the Flask app — do not
run this while control/server/app.py is holding the same port), listens for
StaffTelemetry frames, and logs raw gyro/acc + derived speed/angle for a
fixed duration into a per-phase CSV under docs/imu_capture/.

Usage:
    python3 tools/imu_capture.py <port> <phase_name> [duration_sec]

Example:
    python3 tools/imu_capture.py /dev/cu.usbmodem142201 roll 5
"""
from __future__ import annotations
import csv
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'control', 'server'))
from serial_bridge import SerialBridge  # noqa: E402

BAUD = 115200
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'docs', 'imu_capture')


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    port = sys.argv[1]
    phase = sys.argv[2]
    duration = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f'{phase}.csv')

    rows = []

    def on_telemetry(data: dict):
        if data.get('_type') in ('mic_telemetry', 'pedal_event'):
            return
        rows.append({
            't': time.time(),
            'gyroX': data['gyroX'], 'gyroY': data['gyroY'], 'gyroZ': data['gyroZ'],
            'accX': data['accX'], 'accY': data['accY'], 'accZ': data['accZ'],
            'speed': data['speed'], 'angle': data['angle'],
            'spin_cw': data['spin_cw'], 'orientation': data['orientation'],
        })

    bridge = SerialBridge(port, BAUD, on_telemetry)
    bridge.start()

    print(f'[{phase}] connected on {port} — recording for {duration:.0f}s ...')
    t0 = time.time()
    while time.time() - t0 < duration:
        time.sleep(0.05)
    bridge.close()

    if not rows:
        print(f'[{phase}] NO TELEMETRY RECEIVED — check port/pairing.')
        sys.exit(1)

    with open(out_path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    def stats(key):
        vals = [r[key] for r in rows]
        return min(vals), max(vals), sum(vals) / len(vals)

    print(f'[{phase}] {len(rows)} samples -> {out_path}')
    for axis in ('gyroX', 'gyroY', 'gyroZ'):
        lo, hi, avg = stats(axis)
        print(f'  {axis}: min={lo:.0f} max={hi:.0f} avg={avg:.0f} range={hi - lo:.0f}')


if __name__ == '__main__':
    main()

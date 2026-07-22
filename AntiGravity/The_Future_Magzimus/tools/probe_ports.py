"""Probe candidate serial ports to find which one is the Hub.

Opens each port, sends a MSG_DISCOVER frame, and listens briefly for any
STAFF_TELEMETRY / IDENTITY response coming back through the Hub's bridge.
"""
from __future__ import annotations
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'control', 'server'))
import serial
import protocol as proto
from serial_bridge import SerialBridge

PORTS = [
    '/dev/cu.usbmodem142201',
    '/dev/cu.usbmodem5C371995561',
    '/dev/cu.wchusbserial5C371995561',
]
BAUD = 115200


def probe(port: str, listen_s: float = 4.0):
    hits = {'telemetry': 0, 'identity': 0}

    def on_telemetry(data):
        hits['telemetry'] += 1

    def on_identity(data):
        hits['identity'] += 1
        print(f'    identity: {data}')

    try:
        bridge = SerialBridge(port, BAUD, on_telemetry, on_identity=on_identity)
    except serial.SerialException as e:
        print(f'  {port}: OPEN FAILED — {e}')
        return None

    bridge.start()
    time.sleep(2.5)  # allow ESP32 auto-reset (DTR toggle on port open) to reboot
    bridge.send(proto.pack_discover())
    t0 = time.time()
    while time.time() - t0 < listen_s:
        time.sleep(0.05)
    bridge.close()
    print(f'  {port}: telemetry={hits["telemetry"]} identity={hits["identity"]}')
    return hits


if __name__ == '__main__':
    for p in PORTS:
        print(f'Probing {p} ...')
        probe(p)

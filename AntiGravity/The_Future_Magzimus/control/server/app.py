"""Flask control server — bridges Serial↔WebSocket and exposes REST command API."""
from __future__ import annotations
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO

import protocol as proto
from serial_bridge import SerialBridge
from engine import Engine

# ─── Config ───────────────────────────────────────────────────────────────────
SERIAL_PORT   = os.environ.get('SERIAL_PORT', '/dev/tty.usbserial-0001')
BAUD_RATE     = int(os.environ.get('BAUD_RATE', '115200'))
NUMBER_PATH   = os.environ.get('NUMBER_PATH',
                    os.path.join(os.path.dirname(__file__), '../../numbers/example.json'))
UI_DIR        = os.path.join(os.path.dirname(__file__), '../ui')

# ─── App ──────────────────────────────────────────────────────────────────────
app      = Flask(__name__, static_folder=UI_DIR, static_url_path='')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

bridge: SerialBridge | None = None
engine: Engine | None = None

_discovery_lock    = threading.Lock()
_discovery_results: list[dict] = []


def on_telemetry(data: dict):
    socketio.emit('telemetry', data)
    if engine:
        engine.on_telemetry(data)


def on_identity(data: dict):
    with _discovery_lock:
        seen = {d['deviceId'] for d in _discovery_results}
        if data['deviceId'] not in seen:
            _discovery_results.append(data)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(UI_DIR, 'index.html')


@app.route('/api/command/staff', methods=['POST'])
def cmd_staff():
    body = request.json or {}
    frame = proto.pack_staff_command(
        target_id  = body.get('targetId', 0xFFFF),
        cmd_type   = body.get('cmdType', 1),
        r          = body.get('r', 0),
        g          = body.get('g', 0),
        b          = body.get('b', 0),
        brightness = body.get('brightness', 150),
    )
    if bridge: bridge.send(frame)
    return jsonify({'ok': True})


@app.route('/api/command/relay', methods=['POST'])
def cmd_relay():
    body = request.json or {}
    frame = proto.pack_relay_command(
        target_id   = body.get('targetId', 0xFF),
        state       = body.get('state', 0),
        duration_ms = body.get('durationMs', 0),
    )
    if bridge: bridge.send(frame)
    return jsonify({'ok': True})


@app.route('/api/command/pwm', methods=['POST'])
def cmd_pwm():
    body = request.json or {}
    frame = proto.pack_pwm_command(
        target_id = body.get('targetId', 0xFF),
        w         = body.get('w', 0),
        r         = body.get('r', 0),
        g         = body.get('g', 0),
        b         = body.get('b', 0),
        fade_ms   = body.get('fadeMs', 0),
    )
    if bridge: bridge.send(frame)
    return jsonify({'ok': True})


@app.route('/api/hub/pause', methods=['POST'])
def hub_pause():
    sec = (request.get_json(silent=True) or {}).get('seconds', 10)
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    bridge.send(proto.pack_hub_pause(sec))
    return jsonify({'ok': True, 'pauseSeconds': sec})


@app.route('/api/command/role', methods=['POST'])
def cmd_role():
    body      = request.get_json(silent=True) or {}
    target_id = body.get('targetId', 0xFFFF)
    tx        = bool(body.get('txEnabled', True))
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    bridge.send(proto.pack_role_ctrl(target_id, tx))
    return jsonify({'ok': True, 'targetId': target_id, 'txEnabled': tx})


@app.route('/api/wifi', methods=['POST'])
def wifi_ctrl():
    body      = request.get_json(silent=True) or {}
    state     = 1 if body.get('enable', True) else 0
    target_id = body.get('targetId', 0xFFFF)
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    bridge.send(proto.pack_wifi_ctrl(target_id, state))
    return jsonify({'ok': True, 'state': state, 'targetId': target_id})


@app.route('/api/discover', methods=['POST'])
def discover():
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    timeout = (request.get_json(silent=True) or {}).get('timeout', 2.0)
    with _discovery_lock:
        _discovery_results.clear()
    bridge.send(proto.pack_discover())
    time.sleep(timeout)
    with _discovery_lock:
        return jsonify({'ok': True, 'devices': list(_discovery_results)})


@app.route('/api/slots', methods=['GET'])
def list_slots():
    return jsonify({'ok': True, 'slots': engine._registry.list_slots() if engine else {}})


@app.route('/api/slots', methods=['POST'])
def set_slot():
    body = request.get_json(silent=True) or {}
    slot      = body.get('slot')
    device_id = body.get('deviceId')
    if slot is None or device_id is None:
        return jsonify({'ok': False, 'error': 'slot and deviceId required'}), 400
    if engine:
        engine._registry.set_slot(slot, int(device_id))
    return jsonify({'ok': True, 'slot': slot, 'deviceId': device_id})


@app.route('/api/hotswap', methods=['POST'])
def hotswap():
    body = request.get_json(silent=True) or {}
    slot        = body.get('slot')
    new_id      = body.get('deviceId')
    device_type = body.get('deviceType')   # optional: 'staff' | 'relay' | 'pwm'
    if slot is None or new_id is None:
        return jsonify({'ok': False, 'error': 'slot and deviceId required'}), 400
    if engine:
        engine._registry.hotswap(slot, int(new_id), device_type)
    return jsonify({'ok': True, 'slot': slot, 'newDeviceId': new_id})


@app.route('/api/number/load', methods=['POST'])
def load_number():
    path = (request.json or {}).get('path', NUMBER_PATH)
    try:
        engine.load(path)
        return jsonify({'ok': True, 'path': path})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    def _send_staff(tid, ct, r, g, b, br):
        if bridge: bridge.send(proto.pack_staff_command(tid, ct, r, g, b, br))

    def _send_relay(tid, st, ms):
        if bridge: bridge.send(proto.pack_relay_command(tid, st, ms))

    def _send_pwm(tid, w, r, g, b, ms):
        if bridge: bridge.send(proto.pack_pwm_command(tid, w, r, g, b, ms))

    engine = Engine(_send_staff, _send_relay, _send_pwm)
    engine.load(NUMBER_PATH)

    try:
        bridge = SerialBridge(SERIAL_PORT, BAUD_RATE, on_telemetry, on_identity)
        bridge.start()
        print(f'Serial connected: {SERIAL_PORT}')
    except Exception as e:
        print(f'Serial unavailable ({e}) — running without hardware')

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

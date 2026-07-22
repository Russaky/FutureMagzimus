"""Flask control server — bridges Serial↔WebSocket and exposes REST command API."""
from __future__ import annotations
import glob
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))

from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO

import serial
import serial.tools.list_ports as list_ports

import protocol as proto
from serial_bridge import SerialBridge
from engine import Engine
import bank_manager
import effects_library

# ─── Config ───────────────────────────────────────────────────────────────────
# SERIAL_PORT: אם לא הוגדר במפורש, ה-Hub מאותר אוטומטית (ראה _guess_hub_port).
SERIAL_PORT   = os.environ.get('SERIAL_PORT')
BAUD_RATE     = int(os.environ.get('BAUD_RATE', '115200'))
HUB_RECONNECT_INTERVAL_SEC = 2
# Demo Number (example.json: speed>2.0 -> red/blue/off) used to auto-load here and
# INTERRUPT any manual/Bank/Effects Lab command on the staff the moment it moved —
# the exact "blue-red-off" behavior reported by the user. Nothing should auto-fire
# by default; numbers/stress-test.json has zero events. Load a real Number
# explicitly via POST /api/number/load when you actually want one running.
NUMBER_PATH   = os.environ.get('NUMBER_PATH',
                    os.path.join(os.path.dirname(__file__), '../../numbers/stress-test.json'))
DEVICE_OFFLINE_MS = 5000

FX_LIBRARY_PATH = os.path.join(os.path.dirname(__file__), '../../effects/effects.json')
fx_store = effects_library.EffectStore(FX_LIBRARY_PATH)
UI_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), '../ui'))

# ─── App ──────────────────────────────────────────────────────────────────────
# UI disabled — control/ui/ kept on disk for future reference but not served.
app      = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

bridge: SerialBridge | None = None
engine: Engine | None = None

# ─── Hub connection management ────────────────────────────────────────────────
# ה-Hub מתחבר/מתנתק פיזית הרבה (USB), גם באמצע הפעלה. bridge=None בכל רגע
# פירושו "לא מחובר עכשיו" — לא נכשל-לצמיתות. _hub_watchdog מנסה להתחבר מחדש
# אוטומטית כל HUB_RECONNECT_INTERVAL_SEC כל עוד לא בוצע ניתוק ידני מפורש.
_hub_lock             = threading.Lock()
_hub_port: str | None = None
_hub_last_error: str | None = None
_hub_manual_disconnect = False

# מדורג לפי רמת ביטחון: שבבי גשר UART חיצוניים (CH340/CH9102/CP210, למשל
# WCH שמחווט בפועל על ה-Hub) הם כמעט תמיד הפורט הנכון. פורט "usbmodem" גנרי
# יכול להיות גם ה-USB הנטיבי (JTAG/debug) של אותו בקר — לא תקין לתקשורת מול
# ה-Hub, ראה docs/agent/DONE.md 2026-07-16 ("ה-Hub חובר בטעות לפורט הנטיבי").
# לכן usbmodem/uart בטיר נמוך יותר, אחרי usbserial/שמות שבב מפורשים.
_HUB_PORT_TIERS = (
    ('ch9102', 'ch340', 'wch', 'cp210'),
    ('usbserial',),
    ('usbmodem', 'uart'),
)


def _guess_hub_port() -> str | None:
    """Best-effort auto-detect across confidence tiers; falls back to the first
    non-Bluetooth port if nothing matches a known USB-serial bridge chip."""
    ports = list(list_ports.comports())
    for tier in _HUB_PORT_TIERS:
        for p in ports:
            text = f'{p.device} {p.description}'.lower()
            if any(hint in text for hint in tier):
                return p.device
    for p in ports:
        if 'bluetooth' not in p.device.lower():
            return p.device
    return None


def _hub_status_payload() -> dict:
    return {
        'connected': bridge is not None,
        'port':      _hub_port,
        'error':     _hub_last_error,
    }


def _emit_hub_status():
    socketio.emit('hub_status', _hub_status_payload())


def _on_hub_lost():
    """Called from SerialBridge's own thread when the physical port disappears."""
    global bridge, _hub_port, _hub_last_error
    with _hub_lock:
        if bridge is None:
            return
        bridge = None
        _hub_port = None
        _hub_last_error = 'החיבור ל-Hub אבד (נותק פיזית?)'
    print(f'Hub connection lost — will keep retrying every {HUB_RECONNECT_INTERVAL_SEC}s')
    _emit_hub_status()


def _connect_hub(port: str | None = None) -> tuple[bool, str | None]:
    """Try to (re)connect to the Hub. Idempotent — returns True immediately if
    already connected. Safe to call from the watchdog on every tick."""
    global bridge, _hub_port, _hub_last_error, _hub_manual_disconnect
    with _hub_lock:
        if bridge is not None:
            return True, None
        chosen = port or SERIAL_PORT or _guess_hub_port()
        if not chosen:
            _hub_last_error = 'לא נמצא אף פורט Serial מחובר'
            return False, _hub_last_error
        try:
            new_bridge = SerialBridge(chosen, BAUD_RATE, on_telemetry,
                                       on_identity, on_mic_telemetry,
                                       on_pedal_event, on_effect_list,
                                       on_disconnect=_on_hub_lost)
            new_bridge.start()
            bridge = new_bridge
            _hub_port = chosen
            _hub_last_error = None
            _hub_manual_disconnect = False
        except Exception as e:
            _hub_last_error = str(e)
            return False, str(e)
    print(f'Hub connected: {chosen}')
    _emit_hub_status()
    return True, None


def _disconnect_hub():
    """Explicit user-requested disconnect — the watchdog will NOT auto-reconnect
    until /api/hub/connect is called again."""
    global bridge, _hub_port, _hub_manual_disconnect, _hub_last_error
    with _hub_lock:
        if bridge is not None:
            try:
                bridge.close()
            except Exception:
                pass
        bridge = None
        _hub_port = None
        _hub_last_error = None
        _hub_manual_disconnect = True
    print('Hub disconnected (manual)')
    _emit_hub_status()


def _hub_watchdog():
    """Background auto-reconnect loop — picks the Hub back up shortly after a
    physical replug without requiring any UI action."""
    while True:
        time.sleep(HUB_RECONNECT_INTERVAL_SEC)
        if bridge is None and not _hub_manual_disconnect:
            _connect_hub()


_discovery_lock    = threading.Lock()
_discovery_results: list[dict] = []
_effect_registry:  dict[str, list] = {}  # deviceId → [{'effectId':…, 'name':…}]

# ─── Network Dashboard: in-memory device state + Tx/Rx traffic log ───────────
_devices_lock = threading.Lock()
_devices: dict[str, dict] = {}   # deviceId (hex string) → {role, ip, firmware, lastSeen, ...}
_traffic:  deque = deque(maxlen=300)

# ─── Measurement Campaign: server-side raw JSONL recorder ────────────────────
# See docs/SmartStaff_Measurement_Campaign_v2.md — the UI documents, the file is
# the source of truth. No analysis/calculation happens here.
MEASUREMENTS_DIR = os.path.realpath(os.path.join(os.path.dirname(__file__), '../../docs/measurements'))
MEASUREMENTS_META_PATH = os.path.join(MEASUREMENTS_DIR, '_meta.json')
_recording_lock = threading.Lock()
_recording: dict = {'active': False, 'stage': None, 'path': None, 'fh': None,
                     'start_ts': None, 'count': 0}
_meta_lock = threading.Lock()


def _norm_device_id(device_id) -> str:
    if isinstance(device_id, str):
        return device_id.upper()
    return f'{int(device_id):04X}'


def _touch_device(device_id, **fields) -> dict:
    """Update/create a device record and broadcast the change to the dashboard."""
    did = _norm_device_id(device_id)
    with _devices_lock:
        rec = _devices.setdefault(did, {'id': did})
        
        # Merge sub-dictionary fields like 'state', 'last_rx', 'last_tx'
        for k, v in fields.items():
            if v is None:
                continue
            if k in ('state', 'last_rx', 'last_tx') and isinstance(v, dict) and isinstance(rec.get(k), dict):
                rec[k].update(v)
            else:
                rec[k] = v
                
        rec['lastSeen'] = time.time() * 1000
        rec['online']   = True
        
        # Resolve slot and controller mapping
        controlled_by = rec.get('controlled_by', 'Hub')
        role = rec.get('role', 'unknown')
        try:
            did_int = int(did, 16)
            # Check slot mapping
            slot_name = None
            if engine:
                with engine._registry._lock:
                    for s_name, s_id in engine._registry._slots.items():
                        if s_id == did_int:
                            slot_name = s_name
                            break
            if slot_name:
                rec['slot'] = slot_name
                
            # Check if active timeline is running
            is_timeline_active = False
            if engine:
                with engine._registry._lock:
                    is_timeline_active = (role, did_int) in engine._registry._active
            if is_timeline_active:
                controlled_by = 'Mac/Hub Timeline'
            else:
                if role == 'pwm':
                    last_tx_ts = rec.get('last_tx', {}).get('ts', 0)
                    now_ms = time.time() * 1000
                    if now_ms - last_tx_ts < 5000:
                        controlled_by = 'Mac/Hub (Manual)'
                    else:
                        controlled_by = 'Staff (Autonomous Link)'
                elif role == 'staff':
                    controlled_by = 'Standalone (IMU)'
                else:
                    controlled_by = 'Hub'
        except Exception:
            pass
            
        rec['controlled_by'] = controlled_by
        snapshot = dict(rec)
    socketio.emit('device_update', snapshot)
    return snapshot


def _record_frame(frame_type: str, data: dict):
    """Append a raw telemetry frame to the active measurement recording, if any.
    No parsing/derivation beyond what already arrived — raw in, raw out."""
    if frame_type != 'staff_telemetry':
        return
    with _recording_lock:
        if not _recording['active']:
            return
        line = {'t_arrival': time.time() * 1000, 'type': 'telemetry', 'data': data}
        _recording['fh'].write(json.dumps(line) + '\n')
        _recording['count'] += 1


def _log_traffic(direction: str, msg_type: str, device_id=None, detail: str = ''):
    entry = {
        'ts':       time.time() * 1000,
        'dir':      direction,           # 'TX' | 'RX'
        'type':     msg_type,
        'deviceId': _norm_device_id(device_id) if device_id is not None else None,
        'detail':   detail,
    }
    _traffic.append(entry)
    socketio.emit('net_traffic', entry)


def _tx(frame: bytes, device_id=None, detail: str = ''):
    """Send a frame to the Hub over Serial and log it as outgoing (TX) traffic."""
    if bridge:
        try:
            bridge.send(frame)
        except serial.SerialException:
            pass  # _on_hub_lost already flipped bridge to None and notified the UI
    msg_type = frame[2] if len(frame) > 2 else -1
    _log_traffic('TX', proto.MSG_NAMES.get(msg_type, f'0x{msg_type:02X}'), device_id=device_id, detail=detail)
    
    # Store last_tx inside the device record
    if device_id is not None:
        did = _norm_device_id(device_id)
        with _devices_lock:
            # If broadcast, update for all matching devices
            if device_id in (0xFFFF, 0xFF):
                role_map = {
                    proto.MSG_CMD_STAFF: 'staff',
                    proto.MSG_CMD_RELAY: 'relay',
                    proto.MSG_CMD_PWM: 'pwm',
                    proto.MSG_CMD_PROGRESS: 'progressbar',
                }
                target_role = role_map.get(msg_type)
                for rec in _devices.values():
                    if target_role is None or rec.get('role') == target_role:
                        rec['last_tx'] = {
                            'ts': time.time() * 1000,
                            'cmd': proto.MSG_NAMES.get(msg_type, f'0x{msg_type:02X}'),
                            'detail': detail
                        }
            else:
                rec = _devices.setdefault(did, {'id': did})
                rec['last_tx'] = {
                    'ts': time.time() * 1000,
                    'cmd': proto.MSG_NAMES.get(msg_type, f'0x{msg_type:02X}'),
                    'detail': detail
                }


def _device_watchdog():
    """Flip devices to offline once they exceed DEVICE_OFFLINE_MS without a heartbeat."""
    while True:
        time.sleep(1.0)
        now = time.time() * 1000
        with _devices_lock:
            stale = [rec for rec in _devices.values()
                     if rec.get('online') and now - rec.get('lastSeen', 0) > DEVICE_OFFLINE_MS]
            for rec in stale:
                rec['online'] = False
            snapshots = [dict(rec) for rec in stale]
        for snap in snapshots:
            socketio.emit('device_update', snap)

NUMBERS_DIR  = os.path.realpath(os.path.join(os.path.dirname(__file__), '../../numbers'))
FIRMWARE_DIR = os.path.join(os.path.dirname(__file__), '../../firmware')
BUILDS_DIR   = os.path.realpath(os.path.join(os.path.dirname(__file__), '../../firmware/builds'))

# PlatformIO's venv isn't on PATH when this server is launched outside an
# interactive shell (e.g. IDE task, start.sh) — resolve it explicitly so
# firmware build/OTA-flash subprocess calls don't fail with "not found".
PIO_BIN = shutil.which('pio') or os.path.expanduser('~/.platformio/penv/bin/pio')
os.makedirs(BUILDS_DIR, exist_ok=True)

_ota_lock   = threading.Lock()
_build_lock = threading.Lock()

_FIRMWARE_ENV_MAP = {
    'staff':       'staff',
    'relay':       'relay',
    'pwm':         'pwm',
    'hub':         'hub',
    'progressbar': 'progressbar',
    'mic':         'mic',
    'pedal':       'pedal',
}

# fw_key → {dir, env}  (env used for `pio run -e <env>`)
_FIRMWARE_BUILD_MAP: dict[str, dict] = {
    'staff':       {'dir': 'staff',       'env': 'staff'},
    'staff-c3':    {'dir': 'staff',       'env': 'staff-c3'},
    'relay':       {'dir': 'relay',       'env': 'relay'},
    'pwm':         {'dir': 'pwm',         'env': 'pwm'},
    'hub':         {'dir': 'hub',         'env': 'hub-esp32'},
    'progressbar': {'dir': 'progressbar', 'env': 'progressbar'},
    'mic':         {'dir': 'mic',         'env': 'mic'},
    'pedal':       {'dir': 'pedal',       'env': 'pedal'},
}

_EFFECT_PRESETS_H = os.path.join(FIRMWARE_DIR, 'staff', 'include', 'EffectPresets.h')

def _write_effect_presets(presets: dict):
    flame_hue   = int(presets.get('flameHueMax',   28))
    flame_bmin  = int(presets.get('flameBrightMin', 120))
    flame_smin  = int(presets.get('flameSatMin',    210))
    rainbow_step = int(presets.get('rainbowStep',    3))
    sparkle_fade = int(presets.get('sparkleFade',   180))
    content = (
        '#pragma once\n'
        '// Auto-generated by Firmware Builder — do not edit manually\n'
        f'#define PRESET_FLAME_HUE_MAX     {flame_hue}\n'
        f'#define PRESET_FLAME_BRIGHT_MIN  {flame_bmin}\n'
        f'#define PRESET_FLAME_SAT_MIN     {flame_smin}\n'
        f'#define PRESET_RAINBOW_STEP      {rainbow_step}\n'
        f'#define PRESET_SPARKLE_FADE      {sparkle_fade}\n'
    )
    with open(_EFFECT_PRESETS_H, 'w') as f:
        f.write(content)


_ROLE_BY_TYPE = {'mic_telemetry': 'mic', 'pedal_event': 'pedal', 'staff_telemetry': 'staff'}


def on_telemetry(data: dict):
    socketio.emit('telemetry', data)
    t = data.get('_type', 'staff_telemetry')
    _record_frame(t, data)
    detail = (f"eventType={data['eventType']}" if t == 'pedal_event' else
              f"rms={data.get('rms')} peak={data.get('peak')}" if t == 'mic_telemetry' else
              f"speed={data.get('speed')} angle={data.get('angle')}")
    
    # Store telemetry data into _devices
    state_dict = {}
    if t == 'staff_telemetry':
        state_dict = {
            'speed': data.get('speed'),
            'angle': data.get('angle'),
            'orientation': data.get('orientation'),
            'throw': data.get('throw'),
            'catch': data.get('catch'),
            'spin_cw': data.get('spin_cw'),
            'impact': data.get('impact'),
            'motionType': data.get('motionType'),
        }
    elif t == 'mic_telemetry':
        state_dict = {
            'rms': data.get('rms'),
            'peak': data.get('peak'),
            'frequency': data.get('frequency'),
        }
    elif t == 'pedal_event':
        state_dict = {
            'eventType': data.get('eventType'),
        }
        
    last_rx_info = {
        'ts': time.time() * 1000,
        'data': data
    }
    
    _touch_device(data.get('deviceId', 0), role=_ROLE_BY_TYPE.get(t, 'staff'), state=state_dict, last_rx=last_rx_info)
    
    _log_traffic('RX', proto.MSG_NAMES.get(
        {'mic_telemetry': proto.MSG_MIC_TELEMETRY, 'pedal_event': proto.MSG_PEDAL_EVENT}
        .get(t, proto.MSG_STAFF_TELEMETRY)), device_id=data.get('deviceId', 0), detail=detail)
    if engine:
        if t == 'mic_telemetry':
            engine.on_mic_telemetry(data)
        elif t == 'pedal_event':
            engine.on_pedal_event(data)
        else:
            engine.on_telemetry(data)


def on_identity(data: dict):
    with _discovery_lock:
        seen = {d['deviceId'] for d in _discovery_results}
        if data['deviceId'] not in seen:
            _discovery_results.append(data)
    _touch_device(data['deviceId'], role=data.get('role'), firmware=data.get('firmware'), ip=data.get('ip'))
    _log_traffic('RX', proto.MSG_NAMES[proto.MSG_IDENTITY], device_id=data['deviceId'],
                 detail=f"role={data.get('role')} ip={data.get('ip')}")
    socketio.emit('identity', data)


def on_mic_telemetry(data: dict):
    socketio.emit('mic_telemetry', data)
    if engine:
        engine.on_mic_telemetry(data)


def on_pedal_event(data: dict):
    socketio.emit('pedal_event', data)
    if engine:
        engine.on_pedal_event(data)


def on_effect_list(data: dict):
    did = str(data.get('deviceId', ''))
    _effect_registry[did] = data.get('effects', [])
    _touch_device(data.get('deviceId', 0))
    _log_traffic('RX', proto.MSG_NAMES[proto.MSG_EFFECT_LIST], device_id=data.get('deviceId', 0),
                 detail=f"{len(data.get('effects', []))} effects")
    socketio.emit('effect_list', data)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(UI_DIR, 'index.html')


# ─── Network Dashboard — device monitor + Tx/Rx console ──────────────────────
# Only these specific UI files are served (control/ui/ as a whole stays disabled,
# see docs/agent/DONE.md 2026-06-08).

@app.route('/dashboard.html')
def dashboard_page():
    return send_from_directory(UI_DIR, 'dashboard.html')


@app.route('/measure.html')
def measure_page():
    return send_from_directory(UI_DIR, 'measure.html')


@app.route('/onboarding.html')
def onboarding_page():
    return send_from_directory(UI_DIR, 'onboarding.html')


@app.route('/bank.html')
def bank_page():
    return send_from_directory(UI_DIR, 'bank.html')


@app.route('/effects.html')
def effects_page():
    return send_from_directory(UI_DIR, 'effects.html')


@app.route('/nav.js')
def dashboard_nav():
    return send_from_directory(UI_DIR, 'nav.js')


@app.route('/shared.css')
def dashboard_css():
    return send_from_directory(UI_DIR, 'shared.css')


@app.route('/api/network/devices', methods=['GET'])
def network_devices():
    now = time.time() * 1000
    with _devices_lock:
        devices = []
        for rec in _devices.values():
            snap = dict(rec)
            snap['online'] = bool(snap.get('online')) and (now - snap.get('lastSeen', 0) <= DEVICE_OFFLINE_MS)
            devices.append(snap)
    return jsonify({'ok': True, 'devices': devices, 'offlineTimeoutMs': DEVICE_OFFLINE_MS})


@app.route('/api/network/traffic', methods=['GET'])
def network_traffic():
    return jsonify({'ok': True, 'traffic': list(_traffic)})


# ─── Measurement Campaign — recording control ─────────────────────────────────
@app.route('/api/measure/start', methods=['POST'])
def measure_start():
    body  = request.get_json(silent=True) or {}
    stage = str(body.get('stage', '')).strip()
    if not stage:
        return jsonify({'ok': False, 'error': 'stage is required'}), 400
    with _recording_lock:
        if _recording['active']:
            return jsonify({'ok': False, 'error': f"already recording ({_recording['stage']})"}), 409
        os.makedirs(MEASUREMENTS_DIR, exist_ok=True)
        ts = time.strftime('%Y%m%d-%H%M%S')
        fname = f'{ts}_{stage}.jsonl'
        path = os.path.join(MEASUREMENTS_DIR, fname)
        fh = open(path, 'w')
        fh.write(json.dumps({'type': 'session_start', 'stage': stage, 'ts': time.time() * 1000}) + '\n')
        _recording.update(active=True, stage=stage, path=path, fh=fh,
                           start_ts=time.time() * 1000, count=0)
    return jsonify({'ok': True, 'stage': stage, 'file': fname})


@app.route('/api/measure/mark', methods=['POST'])
def measure_mark():
    body  = request.get_json(silent=True) or {}
    label = str(body.get('label', 'mark'))
    with _recording_lock:
        if not _recording['active']:
            return jsonify({'ok': False, 'error': 'not recording'}), 409
        _recording['fh'].write(json.dumps(
            {'type': 'marker', 'label': label, 't_arrival': time.time() * 1000}) + '\n')
    return jsonify({'ok': True, 'label': label})


@app.route('/api/measure/stop', methods=['POST'])
def measure_stop():
    with _recording_lock:
        if not _recording['active']:
            return jsonify({'ok': False, 'error': 'not recording'}), 409
        _recording['fh'].write(json.dumps({'type': 'session_end', 'ts': time.time() * 1000,
                                            'count': _recording['count']}) + '\n')
        _recording['fh'].close()
        result = {'stage': _recording['stage'], 'file': os.path.basename(_recording['path']),
                   'count': _recording['count']}
        _recording.update(active=False, stage=None, path=None, fh=None, start_ts=None, count=0)
    return jsonify({'ok': True, **result})


@app.route('/api/measure/status', methods=['GET'])
def measure_status():
    with _recording_lock:
        return jsonify({'ok': True, 'active': _recording['active'], 'stage': _recording['stage'],
                         'startTs': _recording['start_ts'], 'count': _recording['count']})


@app.route('/api/measure/meta', methods=['GET'])
def measure_meta_get():
    with _meta_lock:
        if not os.path.isfile(MEASUREMENTS_META_PATH):
            return jsonify({'ok': True, 'meta': {}})
        with open(MEASUREMENTS_META_PATH) as f:
            return jsonify({'ok': True, 'meta': json.load(f)})


@app.route('/api/measure/meta', methods=['POST'])
def measure_meta_set():
    """Manually-entered facts that belong to the campaign as a whole (not a single
    recording) — e.g. r measured with a tape measure in M1a. Merged, not replaced."""
    body = request.get_json(silent=True) or {}
    with _meta_lock:
        meta = {}
        if os.path.isfile(MEASUREMENTS_META_PATH):
            with open(MEASUREMENTS_META_PATH) as f:
                meta = json.load(f)
        for k, v in body.items():
            meta[k] = {'value': v, 'ts': time.time() * 1000}
        os.makedirs(MEASUREMENTS_DIR, exist_ok=True)
        with open(MEASUREMENTS_META_PATH, 'w') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    return jsonify({'ok': True, 'meta': meta})


@app.route('/api/measure/files', methods=['GET'])
def measure_files():
    os.makedirs(MEASUREMENTS_DIR, exist_ok=True)
    files = []
    for name in sorted(os.listdir(MEASUREMENTS_DIR), reverse=True):
        if name.endswith('.jsonl'):
            p = os.path.join(MEASUREMENTS_DIR, name)
            files.append({'name': name, 'size': os.path.getsize(p)})
    return jsonify({'ok': True, 'files': files})


def _valid_measure_name(name: str) -> bool:
    return bool(name) and '/' not in name and '\\' not in name and name.endswith('.jsonl')


@app.route('/api/measure/download/<path:name>', methods=['GET'])
def measure_download(name):
    if not _valid_measure_name(name):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400
    return send_from_directory(MEASUREMENTS_DIR, name, as_attachment=True)


@app.route('/api/measure/view/<path:name>', methods=['GET'])
def measure_view(name):
    """Raw file content for in-page preview (no download prompt) — used by the 'load' action."""
    if not _valid_measure_name(name):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400
    return send_from_directory(MEASUREMENTS_DIR, name, as_attachment=False, mimetype='text/plain')


@app.route('/api/measure/files/<path:name>', methods=['DELETE'])
def measure_delete(name):
    if not _valid_measure_name(name):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400
    with _recording_lock:
        if _recording['active'] and _recording['path'] and os.path.basename(_recording['path']) == name:
            return jsonify({'ok': False, 'error': 'cannot delete the file currently being recorded'}), 409
    path = os.path.join(MEASUREMENTS_DIR, name)
    if not os.path.isfile(path):
        return jsonify({'ok': False, 'error': 'not found'}), 404
    os.remove(path)
    return jsonify({'ok': True, 'file': name})


@app.route('/api/command/staff', methods=['POST'])
def cmd_staff():
    body = request.json or {}
    try:
        target_id = int(body.get('targetId', 0xFFFF))
        cmd_type  = int(body.get('cmdType', 1))
        r         = int(body.get('r', 0))
        g         = int(body.get('g', 0))
        b         = int(body.get('b', 0))
        brightness = int(body.get('brightness', 150))
        frame = proto.pack_staff_command(
            target_id  = target_id,
            cmd_type   = cmd_type,
            r          = r,
            g          = g,
            b          = b,
            brightness = brightness,
        )
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    _tx(frame, device_id=target_id, detail=f"cmdType={cmd_type} rgb=({r},{g},{b}) br={brightness}")
    return jsonify({'ok': True})


@app.route('/api/command/relay', methods=['POST'])
def cmd_relay():
    body = request.json or {}
    try:
        target_id   = int(body.get('targetId', 0xFF))
        state       = int(body.get('state', 0))
        duration_ms = int(body.get('durationMs', 0))
        frame = proto.pack_relay_command(
            target_id   = target_id,
            state       = state,
            duration_ms = duration_ms,
        )
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    _tx(frame, device_id=target_id, detail=f"state={state} dur={duration_ms}ms")
    return jsonify({'ok': True})


@app.route('/api/command/pwm', methods=['POST'])
def cmd_pwm():
    body = request.json or {}
    try:
        target_id = int(body.get('targetId', 0xFF))
        w         = int(body.get('w', 0))
        r         = int(body.get('r', 0))
        g         = int(body.get('g', 0))
        b         = int(body.get('b', 0))
        fade_ms   = int(body.get('fadeMs', 0))
        frame = proto.pack_pwm_command(
            target_id = target_id,
            w         = w,
            r         = r,
            g         = g,
            b         = b,
            fade_ms   = fade_ms,
        )
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    _tx(frame, device_id=target_id, detail=f"wrgb=({w},{r},{g},{b}) fade={fade_ms}ms")
    return jsonify({'ok': True})


@app.route('/api/command/dmx', methods=['POST'])
def cmd_dmx():
    body = request.json or {}
    try:
        target_addr = int(body.get('targetAddr', 1))
        w           = int(body.get('w', 0))
        r           = int(body.get('r', 0))
        g           = int(body.get('g', 0))
        b           = int(body.get('b', 0))
        frame = proto.pack_dmx_command(
            target_addr = target_addr,
            w           = w,
            r           = r,
            g           = g,
            b           = b,
        )
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    _tx(frame, detail=f"addr={target_addr} wrgb=({w},{r},{g},{b})")
    return jsonify({'ok': True})


@app.route('/api/command/effect', methods=['POST'])
def cmd_effect():
    """Generic parametrized FastLED effect on Staff — separate command family
    from /api/command/staff's 6 fixed CmdType effects (Solid/Sparkle/Flame/
    Rainbow/Vertical/Off). See proto.FX_*/PAL_* for template/palette ids."""
    body = request.json or {}
    try:
        target_id   = int(body.get('targetId', 0xFFFF))
        template_id = int(body.get('templateId', 0))
        palette_id  = int(body.get('paletteId', 0))
        speed       = int(body.get('speed', 128))
        intensity   = int(body.get('intensity', 200))
        param1      = int(body.get('param1', 0))
        param2      = int(body.get('param2', 0))
        reactive_source = int(body.get('reactiveSource', 0))
        reactive_param  = int(body.get('reactiveParam', 0))
        frame = proto.pack_effect_command(
            target_id   = target_id,
            template_id = template_id,
            palette_id  = palette_id,
            speed       = speed,
            intensity   = intensity,
            param1      = param1,
            param2      = param2,
            reactive_source = reactive_source,
            reactive_param  = reactive_param,
        )
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    _tx(frame, device_id=target_id,
        detail=f"template={template_id} palette={palette_id} speed={speed} intensity={intensity}")
    return jsonify({'ok': True})


# ─── Effects Library — saved, named, device-scoped presets ──────────────────
# See control/engine/effects_library.py for the schema. Editing/saving here
# never touches firmware — it only stores parameter presets that get sent
# through the same command endpoints above (staff/dmx/pwm/progress).

@app.route('/api/fx', methods=['GET'])
def fx_list():
    return jsonify({'ok': True, 'effects': fx_store.list()})


@app.route('/api/fx', methods=['POST'])
def fx_create():
    body = request.json or {}
    name = (body.get('name') or '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name is required'}), 400
    fields = {k: v for k, v in body.items() if k != 'id'}
    return jsonify({'ok': True, 'effect': fx_store.create(fields)})


@app.route('/api/fx/<fx_id>', methods=['GET'])
def fx_get(fx_id):
    effect = fx_store.get(fx_id)
    if effect is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'effect': effect})


@app.route('/api/fx/<fx_id>', methods=['PUT'])
def fx_update(fx_id):
    body = request.json or {}
    fields = {k: v for k, v in body.items() if k != 'id'}
    effect = fx_store.update(fx_id, fields)
    if effect is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'effect': effect})


@app.route('/api/fx/<fx_id>', methods=['DELETE'])
def fx_delete(fx_id):
    if not fx_store.delete(fx_id):
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True})


def _dispatch_effect(effect: dict):
    """Send a saved effect preset to real hardware right now — reuses the
    exact same pack_* functions as the one-shot /api/command/* routes.

    Effects don't store a target — which physical device an effect actually
    drives is chosen later, when it's attached to a trigger's action in
    Banks. 'Test' here always broadcasts to every device of that type."""
    device_type = effect.get('deviceType', 'staff')
    default_target = {'staff': 0xFFFF, 'dmx': 1, 'pwm': 0xFF, 'progressbar': 0xFF}
    target_id = int(effect.get('targetId', default_target.get(device_type, 0xFFFF)))

    if device_type == 'staff':
        frame = proto.pack_effect_command(
            target_id, int(effect.get('templateId', 0)), int(effect.get('paletteId', 0)),
            int(effect.get('speed', 128)), int(effect.get('intensity', 200)),
            int(effect.get('param1', 0)), int(effect.get('param2', 0)),
            int(effect.get('reactiveSource', 0)), int(effect.get('reactiveParam', 0)),
            int(effect.get('colorMode', 0)),
            int(effect.get('pr', 0)), int(effect.get('pg', 0)), int(effect.get('pb', 0)),
            int(effect.get('sr', 0)), int(effect.get('sg', 0)), int(effect.get('sb', 0)))
        detail = (f"fx generic template={effect.get('templateId')} palette={effect.get('paletteId')}"
                 f" reactive={effect.get('reactiveSource', 0)}->{effect.get('reactiveParam', 0)}")
        _tx(frame, device_id=target_id, detail=detail)
    elif device_type == 'dmx':
        target_addr = int(effect.get('targetId', 1))
        frame = proto.pack_dmx_command(target_addr, int(effect.get('w', 0)), int(effect.get('r', 0)),
                                       int(effect.get('g', 0)), int(effect.get('b', 0)))
        _tx(frame, detail=f"fx dmx addr={target_addr}")
    elif device_type == 'pwm':
        frame = proto.pack_pwm_command(target_id, int(effect.get('w', 0)), int(effect.get('r', 0)),
                                       int(effect.get('g', 0)), int(effect.get('b', 0)),
                                       int(effect.get('fadeMs', 0)))
        _tx(frame, device_id=target_id, detail="fx pwm")
    elif device_type == 'progressbar':
        frame = proto.pack_progress_command(target_id, int(effect.get('mode', 1)), int(effect.get('value', 0)),
                                            int(effect.get('r', 0)), int(effect.get('g', 0)), int(effect.get('b', 0)),
                                            int(effect.get('fadeMs', 0)))
        _tx(frame, device_id=target_id, detail="fx progressbar")
    else:
        raise ValueError(f'unknown deviceType {device_type!r}')


@app.route('/api/fx/<fx_id>/test', methods=['POST'])
def fx_test(fx_id):
    effect = fx_store.get(fx_id)
    if effect is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    try:
        _dispatch_effect(effect)
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    return jsonify({'ok': True})


@app.route('/api/fx/preview', methods=['POST'])
def fx_preview_test():
    """Test-send an unsaved effect (editor 'Test' button before hitting Save)."""
    body = request.json or {}
    try:
        _dispatch_effect(body)
    except (TypeError, ValueError, struct.error) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    return jsonify({'ok': True})


@app.route('/api/hub/status', methods=['GET'])
def hub_status():
    return jsonify({'ok': True, **_hub_status_payload()})


@app.route('/api/hub/scan', methods=['GET'])
def hub_scan():
    ports = [{'device': p.device, 'description': p.description} for p in list_ports.comports()]
    return jsonify({'ok': True, 'ports': ports, 'guess': _guess_hub_port()})


@app.route('/api/hub/connect', methods=['POST'])
def hub_connect():
    global _hub_manual_disconnect
    port = (request.get_json(silent=True) or {}).get('port')
    _hub_manual_disconnect = False
    ok, err = _connect_hub(port)
    return jsonify({'ok': ok, 'error': err, **_hub_status_payload()})


@app.route('/api/hub/disconnect', methods=['POST'])
def hub_disconnect():
    _disconnect_hub()
    return jsonify({'ok': True, **_hub_status_payload()})


@app.route('/api/hub/pause', methods=['POST'])
def hub_pause():
    sec = (request.get_json(silent=True) or {}).get('seconds', 10)
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    _tx(proto.pack_hub_pause(sec), detail=f"pause={sec}s")
    return jsonify({'ok': True, 'pauseSeconds': sec})


@app.route('/api/command/role', methods=['POST'])
def cmd_role():
    body      = request.get_json(silent=True) or {}
    target_id = body.get('targetId', 0xFFFF)
    tx        = bool(body.get('txEnabled', True))
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    _tx(proto.pack_role_ctrl(target_id, tx), device_id=target_id, detail=f"txEnabled={tx}")
    return jsonify({'ok': True, 'targetId': target_id, 'txEnabled': tx})


@app.route('/api/wifi', methods=['POST'])
def wifi_ctrl():
    body      = request.get_json(silent=True) or {}
    state     = 1 if body.get('enable', True) else 0
    target_id = body.get('targetId', 0xFFFF)
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    _tx(proto.pack_wifi_ctrl(target_id, state), device_id=target_id, detail=f"wifiEnable={bool(state)}")
    return jsonify({'ok': True, 'state': state, 'targetId': target_id})


@app.route('/api/discover', methods=['POST'])
def discover():
    if not bridge:
        return jsonify({'ok': False, 'error': 'hub not connected'})
    timeout = (request.get_json(silent=True) or {}).get('timeout', 2.0)
    with _discovery_lock:
        _discovery_results.clear()
    _tx(proto.pack_discover())
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


@app.route('/api/banks/triggers', methods=['GET'])
def bank_triggers():
    """Fixed trigger keys the Bank Manager UI lets you map actions to."""
    return jsonify({'ok': True, 'triggers': bank_manager.FIXED_TRIGGERS,
                     'defaultPriorities': bank_manager.DEFAULT_TRIGGER_PRIORITY})


@app.route('/api/banks', methods=['GET'])
def list_banks():
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    return jsonify({'ok': True, 'banks': engine._bank_store.list(),
                     'activeId': engine._bank_store.active_id})


@app.route('/api/banks', methods=['POST'])
def create_bank():
    body = request.get_json(silent=True) or {}
    name = str(body.get('name', '')).strip()
    if not name:
        return jsonify({'ok': False, 'error': 'name is required'}), 400
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    bank = engine._bank_store.create(name)
    return jsonify({'ok': True, 'bank': bank})


@app.route('/api/banks/<bank_id>', methods=['GET'])
def get_bank(bank_id):
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    bank = engine._bank_store.get(bank_id)
    if bank is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'bank': bank})


@app.route('/api/banks/<bank_id>', methods=['PUT'])
def update_bank(bank_id):
    body       = request.get_json(silent=True) or {}
    name       = body.get('name')
    mappings   = body.get('mappings')
    priorities = body.get('priorities')
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    bank = engine._bank_store.update(bank_id, name=name, mappings=mappings, priorities=priorities)
    if bank is None:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    return jsonify({'ok': True, 'bank': bank})


@app.route('/api/banks/<bank_id>', methods=['DELETE'])
def delete_bank(bank_id):
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    engine._bank_store.delete(bank_id)
    return jsonify({'ok': True, 'id': bank_id})


@app.route('/api/banks/<bank_id>/activate', methods=['POST'])
def activate_bank(bank_id):
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    ok = engine._bank_store.set_active(bank_id)
    if not ok:
        return jsonify({'ok': False, 'error': 'not found'}), 404
    socketio.emit('bank_active_changed', {'activeId': bank_id})
    return jsonify({'ok': True, 'activeId': bank_id})


@app.route('/api/banks/active', methods=['DELETE'])
def deactivate_bank():
    """Clear the Active Bank — no bank-mapped commands fire until one is set again."""
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    engine._bank_store.set_active(None)
    socketio.emit('bank_active_changed', {'activeId': None})
    return jsonify({'ok': True, 'activeId': None})


@app.route('/api/command/progress', methods=['POST'])
def cmd_progress():
    body = request.json or {}
    target_id = body.get('targetId', 0xFF)
    mode      = body.get('mode', 0)
    value     = body.get('value', 0)
    r         = body.get('r', 0)
    g         = body.get('g', 0)
    b         = body.get('b', 0)
    fade_ms   = body.get('fadeMs', 0)
    frame = proto.pack_progress_command(
        target_id = target_id,
        mode      = mode,
        value     = value,
        r         = r,
        g         = g,
        b         = b,
        fade_ms   = fade_ms,
    )
    _tx(frame, device_id=target_id, detail=f"mode={mode} val={value} rgb=({r},{g},{b}) fade={fade_ms}ms")
    return jsonify({'ok': True})


@app.route('/api/command/net_status', methods=['POST'])
def cmd_net_status():
    body   = request.json or {}
    status = body.get('status', proto.NET_STATUS_OK)
    target = body.get('targetId', 0xFF)
    frame  = proto.pack_net_status(target, status)
    _tx(frame, device_id=target, detail=f"netStatus={status}")
    return jsonify({'ok': True})


@app.route('/api/showtimer/start', methods=['POST'])
def showtimer_start():
    body     = request.json or {}
    duration = float(body.get('duration', 60.0))
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503

    def _on_event(name: str, data: dict):
        socketio.emit(name, data)

    engine.set_event_callback(_on_event)
    engine.show_timer_start(duration)
    return jsonify({'ok': True, 'duration': duration})


@app.route('/api/showtimer/stop', methods=['POST'])
def showtimer_stop():
    if engine:
        engine.show_timer_stop()
    return jsonify({'ok': True})


@app.route('/api/accumulator/configure', methods=['POST'])
def accumulator_configure():
    body       = request.json or {}
    decay_rate = float(body.get('decayRate', 0.0))
    if not engine:
        return jsonify({'ok': False, 'error': 'engine not initialized'}), 503
    engine.accumulator_configure(decay_rate)
    return jsonify({'ok': True, 'decayRate': decay_rate})


@app.route('/api/accumulator/pulse', methods=['POST'])
def accumulator_pulse():
    body = request.json or {}
    try:
        amount = float(body.get('amount', 1.0))
    except (TypeError, ValueError) as e:
        return jsonify({'ok': False, 'error': str(e)}), 400
    if engine:
        engine.accumulator_pulse(amount)
    return jsonify({'ok': True, 'value': engine.accumulator_value if engine else 0})


@app.route('/api/accumulator/reset', methods=['POST'])
def accumulator_reset():
    if engine:
        engine.accumulator_reset()
    return jsonify({'ok': True})


@app.route('/api/accumulator/value', methods=['GET'])
def accumulator_value():
    return jsonify({'ok': True, 'value': engine.accumulator_value if engine else 0})


@app.route('/api/effects', methods=['GET'])
def list_effects():
    return jsonify({'ok': True, 'devices': _effect_registry})


@app.route('/api/number/load', methods=['POST'])
def load_number():
    path = (request.json or {}).get('path', NUMBER_PATH)
    try:
        engine.load(path)
        return jsonify({'ok': True, 'path': path})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 400


@app.route('/api/numbers/list', methods=['GET'])
def list_numbers():
    result = []
    pattern = os.path.join(NUMBERS_DIR, '*.json')
    for fpath in sorted(glob.glob(pattern)):
        fname = os.path.basename(fpath)
        if fname.startswith('.'):
            continue
        try:
            with open(fpath) as f:
                data = json.load(f)
            result.append({
                'file':  fname,
                'id':    data.get('id', fname),
                'name':  data.get('name', fname),
                'events': len(data.get('events', [])),
                'path':  fpath,
            })
        except Exception:
            result.append({'file': fname, 'id': fname, 'name': fname, 'events': 0, 'path': fpath})
    return jsonify({'ok': True, 'numbers': result})


@app.route('/api/numbers/save', methods=['POST'])
def save_number():
    body = request.get_json(silent=True) or {}
    data = body.get('data')
    fname = body.get('file')
    if not data or not fname:
        return jsonify({'ok': False, 'error': 'data and file required'}), 400
    fname = os.path.basename(fname)
    if not fname.endswith('.json'):
        fname += '.json'
    fpath = os.path.realpath(os.path.join(NUMBERS_DIR, fname))
    if not fpath.startswith(NUMBERS_DIR + os.sep):
        return jsonify({'ok': False, 'error': 'invalid filename'}), 400
    try:
        with open(fpath, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return jsonify({'ok': True, 'file': fname, 'path': fpath})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/numbers/get', methods=['GET'])
def get_number():
    fname = request.args.get('file', '')
    fname = os.path.basename(fname)
    fpath = os.path.realpath(os.path.join(NUMBERS_DIR, fname))
    if not fpath.startswith(NUMBERS_DIR + os.sep) or not os.path.exists(fpath):
        return jsonify({'ok': False, 'error': 'not found'}), 404

    try:
        with open(fpath) as f:
            data = json.load(f)
        return jsonify({'ok': True, 'data': data})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@app.route('/api/trigger/test', methods=['POST'])
def trigger_test():
    """Inject a synthetic sensor event into the engine to test a trigger node."""
    body = request.get_json(silent=True) or {}
    data = body.get('data', {})
    trigger_type = data.get('triggerType', 'threshold')
    signal       = data.get('signal', 'speed')
    # Build a synthetic telemetry dict that satisfies any condition
    synth = {
        'deviceId':    0xFFFF,
        'speed':       10.0,  'angle': 45.0,
        'throw':       True,  'catch': True,
        'spin_cw':     True,  'orientation': 'vertical',
        'impact':      True,  'flags': 0xFF,
        'rms':         1.0,   'peak': 1.0, 'frequency': 440.0,
        'eventType':   data.get('triggerType', 'short'),
        '_type':       'staff_telemetry',
    }
    if engine:
        engine.on_telemetry(synth)
        engine.on_mic_telemetry({**synth, 'deviceId': 0xFFFF})
        engine.on_pedal_event({**synth, 'deviceId': 0xFFFF})
    return jsonify({'ok': True, 'simulated': True})


@app.route('/api/firmware/build', methods=['POST'])
def firmware_build():
    body    = request.get_json(silent=True) or {}
    fw_key  = body.get('fw', '')
    presets = body.get('presets')  # optional dict of effect preset values

    build_info = _FIRMWARE_BUILD_MAP.get(fw_key)
    if not build_info:
        return jsonify({'ok': False, 'error': f'unknown firmware: {fw_key}'}), 400

    fw_dir = os.path.join(FIRMWARE_DIR, build_info['dir'])
    env    = build_info['env']

    def _run():
        sid = str(uuid.uuid4())[:8]

        def emit_log(text, level='log'):
            socketio.emit('build_log', {'fw': fw_key, 'sid': sid, 'text': text, 'level': level})

        with _build_lock:
            if presets and fw_key in ('staff', 'staff-c3'):
                try:
                    _write_effect_presets(presets)
                    emit_log('EffectPresets.h נכתב', 'info')
                except Exception as exc:
                    emit_log(f'שגיאה בכתיבת EffectPresets.h: {exc}', 'error')

            cmd = [PIO_BIN, 'run', '-e', env]
            emit_log(f'[{sid}] {" ".join(cmd)}', 'info')
            try:
                proc = subprocess.Popen(
                    cmd, cwd=fw_dir,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    emit_log(line.rstrip())
                proc.wait()
                if proc.returncode == 0:
                    src = os.path.join(fw_dir, '.pio', 'build', env, 'firmware.bin')
                    if os.path.exists(src):
                        stamp = time.strftime('%Y%m%d_%H%M%S')
                        dst   = os.path.join(BUILDS_DIR, f'{fw_key}_{stamp}.bin')
                        shutil.copy2(src, dst)
                        emit_log(f'staged → firmware/builds/{os.path.basename(dst)}', 'info')
                    socketio.emit('build_done', {'fw': fw_key, 'sid': sid, 'status': 'done'})
                else:
                    socketio.emit('build_done', {'fw': fw_key, 'sid': sid, 'status': 'error'})
            except Exception as exc:
                emit_log(str(exc), 'error')
                socketio.emit('build_done', {'fw': fw_key, 'sid': sid, 'status': 'error'})

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'ok': True, 'fw': fw_key, 'env': env})


@app.route('/api/firmware/builds', methods=['GET'])
def firmware_builds():
    builds = []
    for fname in sorted(os.listdir(BUILDS_DIR), reverse=True):
        if not fname.endswith('.bin'):
            continue
        fpath = os.path.join(BUILDS_DIR, fname)
        parts = fname[:-4].split('_', 1)
        fw_key = parts[0] if parts else fname
        stamp  = parts[1] if len(parts) > 1 else ''
        builds.append({
            'file':   fname,
            'fw':     fw_key,
            'stamp':  stamp,
            'size':   os.path.getsize(fpath),
            'path':   fpath,
        })
    return jsonify({'ok': True, 'builds': builds})


@app.route('/api/ota/scan', methods=['POST'])
def ota_scan():
    try:
        proc = subprocess.run(
            ['dns-sd', '-B', '_arduino._tcp', 'local.'],
            capture_output=True, text=True, timeout=3
        )
        devices = []
        seen = set()
        for line in proc.stdout.splitlines():
            if '_arduino' in line or 'local' not in line:
                continue
            parts = line.split()
            for p in parts:
                if p.endswith('.') and p not in seen and len(p) > 2:
                    name = p.rstrip('.')
                    seen.add(p)
                    devices.append({'hostname': name + '.local', 'name': name})
        return jsonify({'ok': True, 'devices': devices})
    except subprocess.TimeoutExpired:
        return jsonify({'ok': True, 'devices': []})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/api/ota/flash', methods=['POST'])
def ota_flash():
    body = request.get_json(silent=True) or {}
    jobs = body.get('jobs', [])

    spawned = 0
    for job in jobs:
        env    = job.get('env', '')
        target = job.get('target', '')
        if not env or not target:
            continue

        fw_key = env.split('-')[0]
        fw_dir = os.path.join(FIRMWARE_DIR, _FIRMWARE_ENV_MAP.get(fw_key, fw_key))
        if not os.path.isdir(fw_dir):
            socketio.emit('ota_log', {
                'target': target,
                'text':   f'ERROR: firmware dir not found for {env}',
                'level':  'error',
            })
            continue

        job_id = str(uuid.uuid4())[:8]

        def _spawn(env=env, target=target, fw_dir=fw_dir, job_id=job_id):
            cmd = [PIO_BIN, 'run', '-e', env, '-t', 'upload', '--upload-port', target]
            socketio.emit('ota_log', {
                'target': target, 'jobId': job_id,
                'text':   f'[{job_id}] → {" ".join(cmd)}',
                'level':  'info',
            })
            try:
                proc = subprocess.Popen(
                    cmd, cwd=fw_dir,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                for line in proc.stdout:
                    socketio.emit('ota_log', {
                        'target': target, 'jobId': job_id,
                        'text':   line.rstrip(), 'level': 'log',
                    })
                proc.wait()
                status = 'done' if proc.returncode == 0 else 'error'
            except Exception as exc:
                status = 'error'
                socketio.emit('ota_log', {
                    'target': target, 'jobId': job_id,
                    'text': str(exc), 'level': 'error',
                })
            socketio.emit('ota_done', {
                'target': target, 'jobId': job_id, 'status': status,
            })

        threading.Thread(target=_spawn, daemon=True).start()
        spawned += 1

    return jsonify({'ok': True, 'spawned': spawned})


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    def _send_staff(tid, ct, r, g, b, br):
        print(f"DEBUG OUTGOING STAFF CMD: tid={tid}, ct={ct}, r={r}, g={g}, b={b}, br={br}", flush=True)
        _tx(proto.pack_staff_command(tid, ct, r, g, b, br), device_id=tid, detail=f"Engine staff_cmd cmdType={ct} rgb=({r},{g},{b}) br={br}")

    def _send_relay(tid, st, ms):
        _tx(proto.pack_relay_command(tid, st, ms), device_id=tid, detail=f"Engine relay_cmd state={st} dur={ms}ms")

    def _send_pwm(tid, w, r, g, b, ms):
        _tx(proto.pack_pwm_command(tid, w, r, g, b, ms), device_id=tid, detail=f"Engine pwm_cmd wrgb=({w},{r},{g},{b}) fade={ms}ms")

    def _send_progress(tid, mode, val, r, g, b, ms):
        _tx(proto.pack_progress_command(tid, mode, val, r, g, b, ms), device_id=tid, detail=f"Engine progress_cmd mode={mode} val={val} rgb=({r},{g},{b})")

    def _send_dmx(addr, w, r, g, b):
        _tx(proto.pack_dmx_command(addr, w, r, g, b), detail=f"Engine dmx_cmd addr={addr} wrgb=({w},{r},{g},{b})")

    def _send_effect(tid, template_id, palette_id, speed, intensity, param1, param2, reactive_source, reactive_param,
                     color_mode=0, pr=0, pg=0, pb=0, sr=0, sg=0, sb=0):
        _tx(proto.pack_effect_command(tid, template_id, palette_id, speed, intensity, param1, param2,
                                      reactive_source, reactive_param, color_mode, pr, pg, pb, sr, sg, sb),
            device_id=tid, detail=f"Engine effect_cmd template={template_id} reactive={reactive_source}->{reactive_param}")

    engine = Engine(_send_staff, _send_relay, _send_pwm, _send_progress, _send_dmx,
                    send_effect=_send_effect, resolve_effect=fx_store.get)
    engine.reactive_lights_enabled = True
    engine.load(NUMBER_PATH)

    def _engine_event(name: str, data: dict):
        socketio.emit(name, data)

    engine.set_event_callback(_engine_event)

    ok, err = _connect_hub()
    if not ok:
        print(f'Hub unavailable ({err}) — running without hardware, will keep auto-retrying')

    threading.Thread(target=_device_watchdog, daemon=True).start()
    threading.Thread(target=_hub_watchdog, daemon=True).start()

    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)

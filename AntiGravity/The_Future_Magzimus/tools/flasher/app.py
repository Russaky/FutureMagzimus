#!/usr/bin/env python3
"""MAGZIMUS Flasher — Build and upload firmware via PlatformIO."""
from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import threading

import serial.tools.list_ports
from flask import Flask, jsonify, request, send_from_directory
from flask_socketio import SocketIO

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
FW_ROOT  = os.path.normpath(os.path.join(ROOT_DIR, '..', '..', 'firmware'))
UI_DIR   = os.path.join(ROOT_DIR, 'ui')

FIRMWARES = {
    'hub':          {'env': 'hub',          'dir': 'hub',   'board': 'ESP32-S3', 'desc': 'Gateway — Serial ↔ ESP-NOW (S3)'},
    'hub-esp32':    {'env': 'hub-esp32',    'dir': 'hub',   'board': 'ESP32',    'desc': 'Gateway — Serial ↔ ESP-NOW (ESP32)'},
    'staff':        {'env': 'staff',        'dir': 'staff', 'board': 'ESP32-S3', 'desc': 'Staff — IMU + LEDs'},
    'staff-ota':    {'env': 'staff-ota',    'dir': 'staff', 'board': 'ESP32-S3', 'desc': 'Staff — IMU + LEDs (OTA)', 'ota': True},
    'staff-c3':     {'env': 'staff-c3',     'dir': 'staff', 'board': 'ESP32-C3', 'desc': 'Staff — IMU + LEDs (C3)'},
    'staff-c3-ota': {'env': 'staff-c3-ota', 'dir': 'staff', 'board': 'ESP32-C3', 'desc': 'Staff — IMU + LEDs (C3 OTA)', 'ota': True},
    'relay':        {'env': 'relay',        'dir': 'relay', 'board': 'ESP32',    'desc': 'Relay — Smoke / Electromagnet'},
    'pwm':          {'env': 'pwm',          'dir': 'pwm',   'board': 'ESP32',    'desc': 'PWM — WRGB Lights'},
}


def _find_pio() -> str:
    pio = shutil.which('pio')
    if pio:
        return pio
    fallback = os.path.expanduser('~/.platformio/penv/bin/pio')
    return fallback if os.path.exists(fallback) else 'pio'


PIO = _find_pio()

app      = Flask(__name__, static_folder=UI_DIR, static_url_path='')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

_proc:      subprocess.Popen | None = None
_lock =     threading.Lock()
_ota_procs: dict = {}   # port → Popen (parallel OTA jobs)
_ota_lock = threading.Lock()


# ─── REST ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory(UI_DIR, 'index.html')


@app.route('/api/ports')
def api_ports():
    ports = [
        {'device': p.device, 'description': p.description or p.device}
        for p in sorted(serial.tools.list_ports.comports(), key=lambda p: p.device)
    ]
    return jsonify(ports)


@app.route('/api/firmwares')
def api_firmwares():
    return jsonify(FIRMWARES)


# chip substring → board key used in FIRMWARES
_CHIP_MAP = {
    'esp32-s3': 'ESP32-S3',
    'esp32-c3': 'ESP32-C3',
    'esp32-s2': 'ESP32-S2',
    'esp32':    'ESP32',      # must be last (substring of the others)
}


@app.route('/api/detect', methods=['POST'])
def api_detect():
    port = (request.json or {}).get('port', '')
    if not port:
        return jsonify({'ok': False, 'error': 'no port'})

    esptool = os.path.expanduser(
        '~/.platformio/packages/tool-esptoolpy/esptool.py'
    )
    if not os.path.exists(esptool):
        esptool = shutil.which('esptool.py') or 'esptool.py'

    try:
        out = subprocess.check_output(
            ['python3', esptool, '--port', port,
             '--no-stub', '--connect-attempts', '1', 'chip_id'],
            stderr=subprocess.STDOUT, timeout=10, text=True,
        )
    except subprocess.CalledProcessError as e:
        out = e.output or ''
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

    chip = None
    for line in out.splitlines():
        low = line.lower()
        for key in _CHIP_MAP:
            if key in low:
                chip = _CHIP_MAP[key]
                break
        if chip:
            break

    if not chip:
        return jsonify({'ok': False, 'error': 'chip not identified', 'raw': out[:300]})

    compatible = [name for name, fw in FIRMWARES.items() if fw['board'] == chip]
    return jsonify({'ok': True, 'chip': chip, 'compatible': compatible})


CREDENTIALS_FILE = os.path.normpath(os.path.join(FW_ROOT, 'wifi_credentials.ini'))
CONTROL_SERVER   = os.environ.get('CONTROL_SERVER', 'http://localhost:5000')


@app.route('/api/credentials', methods=['GET'])
def get_credentials():
    try:
        text = open(CREDENTIALS_FILE).read()
        ssid = ''
        for line in text.splitlines():
            m = re.search(r'WIFI_SSID="([^"]*)"', line)
            if m:
                ssid = m.group(1)
        return jsonify({'ok': True, 'ssid': ssid})
    except Exception:
        return jsonify({'ok': True, 'ssid': ''})


@app.route('/api/credentials', methods=['POST'])
def set_credentials():
    body     = request.get_json(silent=True) or {}
    ssid     = body.get('ssid', '').strip()
    password = body.get('password', '').strip()
    ota_pass = body.get('otaPassword', 'magzimus').strip() or 'magzimus'
    if not ssid:
        return jsonify({'ok': False, 'error': 'SSID required'}), 400
    content = (
        '# WiFi + OTA credentials — gitignored\n'
        '[env]\n'
        'build_src_flags =\n'
        f'    \'-D WIFI_SSID="{ssid}"\'\n'
        f'    \'-D WIFI_PASSWORD="{password}"\'\n'
        f'    \'-D OTA_PASSWORD="{ota_pass}"\'\n'
        '\n'
        '[env:staff-ota]\n'
        f'upload_flags = --auth={ota_pass}\n'
        '\n'
        '[env:staff-c3-ota]\n'
        f'upload_flags = --auth={ota_pass}\n'
    )
    with open(CREDENTIALS_FILE, 'w') as f:
        f.write(content)
    return jsonify({'ok': True})


@app.route('/api/mdns', methods=['POST'])
def api_mdns():
    """Discover ArduinoOTA devices via mDNS (_arduino._tcp)."""
    import subprocess, socket
    timeout = (request.get_json(silent=True) or {}).get('timeout', 4.0)

    # Collect service names via dns-sd browse
    try:
        out = subprocess.check_output(
            ['dns-sd', '-B', '_arduino._tcp', 'local.'],
            timeout=timeout, stderr=subprocess.DEVNULL, text=True,
        )
    except subprocess.TimeoutExpired as e:
        out = e.output or (e.stdout or '')
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})

    names = []
    for line in out.splitlines():
        parts = line.split()
        if 'Add' in parts and '_arduino._tcp' in line:
            names.append(parts[-1])

    devices = []
    for name in names:
        hostname = f'{name}.local'
        try:
            ip = socket.getaddrinfo(hostname, None, socket.AF_INET)[0][4][0]
        except Exception:
            ip = None
        devices.append({'hostname': hostname, 'ip': ip or '', 'name': name})

    return jsonify({'ok': True, 'devices': devices})


@app.route('/api/discover', methods=['POST'])
def api_discover():
    import urllib.request, urllib.error
    timeout = (request.json or {}).get('timeout', 2.5)
    try:
        req = urllib.request.Request(
            f'{CONTROL_SERVER}/api/discover',
            data=json.dumps({'timeout': timeout}).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=timeout + 3) as resp:
            return resp.read(), resp.status, {'Content-Type': 'application/json'}
    except urllib.error.URLError as e:
        return jsonify({'ok': False, 'error': f'Control server unreachable: {e.reason}'})


# ─── WebSocket ────────────────────────────────────────────────────────────────

@socketio.on('run')
def handle_run(data: dict):
    fw_name = data.get('firmware', '')
    action  = data.get('action', 'build')
    port    = data.get('port', '')

    if fw_name not in FIRMWARES:
        socketio.emit('log', {'text': f'Unknown firmware: {fw_name}', 'level': 'error'})
        return

    fw  = FIRMWARES[fw_name]
    cmd = [PIO, 'run', '-d', os.path.join(FW_ROOT, fw['dir']), '-e', fw['env']]

    if action == 'upload':
        cmd += ['--target', 'upload']
        if port:
            cmd += ['--upload-port', port]
        _spawn(cmd, action, fw_name)

    elif action == 'ota':
        ota_ip = data.get('otaIp', '').strip()
        if not ota_ip:
            socketio.emit('log', {'text': 'OTA requires an IP address.', 'level': 'error'})
            return
        cmd += ['--target', 'upload', '--upload-protocol', 'espota',
                '--upload-port', ota_ip]
        _spawn_ota(cmd, fw_name, ota_ip)

    else:
        _spawn(cmd, action, fw_name)


def _spawn_ota(cmd: list, fw_name: str, target: str):
    """Launch an OTA job independently — multiple can run in parallel."""
    label = f'OTA:{target}'

    def run():
        socketio.emit('log',    {'text': f'▶ {label}  ({fw_name})', 'level': 'cmd'})
        socketio.emit('status', {'state': 'running', 'action': 'ota',
                                 'firmware': fw_name, 'target': target})
        try:
            env  = {**os.environ, 'PYTHONUNBUFFERED': '1'}
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    bufsize=1, env=env)
            with _ota_lock:
                _ota_procs[target] = proc
            for raw in proc.stdout:
                socketio.emit('log', {'text': f'[{target}] {raw.rstrip()}', 'level': 'out'})
            proc.wait()
            state = 'success' if proc.returncode == 0 else 'error'
            socketio.emit('log', {'text': f'{"✓" if state=="success" else "✗"} {label}', 'level': 'out'})
            socketio.emit('status', {'state': state, 'action': 'ota',
                                     'firmware': fw_name, 'target': target})
        except Exception as e:
            socketio.emit('log', {'text': f'✗ {label}: {e}', 'level': 'error'})
        finally:
            with _ota_lock:
                _ota_procs.pop(target, None)

    threading.Thread(target=run, daemon=True).start()


@socketio.on('kill')
def handle_kill(_):
    global _proc
    killed = 0
    if _proc and _proc.poll() is None:
        _proc.terminate(); killed += 1
    with _ota_lock:
        for p in list(_ota_procs.values()):
            if p.poll() is None:
                p.terminate(); killed += 1
    if killed:
        socketio.emit('log', {'text': f'{killed} process(es) terminated.', 'level': 'warn'})
        socketio.emit('status', {'state': 'idle'})


# ─── Runner ───────────────────────────────────────────────────────────────────

def _spawn(cmd: list, action: str, fw_name: str):
    global _proc

    with _lock:
        if _proc and _proc.poll() is None:
            socketio.emit('log', {'text': 'A process is already running.', 'level': 'warn'})
            return

        socketio.emit('status', {'state': 'running', 'action': action, 'firmware': fw_name})
        socketio.emit('log',    {'text': '$ ' + ' '.join(cmd), 'level': 'cmd'})

        def run():
            global _proc
            try:
                env = {**os.environ, 'PYTHONUNBUFFERED': '1'}
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    env=env,
                )
                _proc = proc
                for raw in proc.stdout:
                    socketio.emit('log', {'text': raw.rstrip(), 'level': 'out'})
                proc.wait()
                state = 'success' if proc.returncode == 0 else 'error'
                socketio.emit('status', {
                    'state': state, 'action': action,
                    'firmware': fw_name, 'code': proc.returncode,
                })
            except FileNotFoundError:
                socketio.emit('log', {'text': f'PlatformIO not found: {PIO}', 'level': 'error'})
                socketio.emit('status', {'state': 'error', 'action': action, 'firmware': fw_name})

        threading.Thread(target=run, daemon=True).start()


if __name__ == '__main__':
    print(f'Flasher  →  http://localhost:5001')
    print(f'PIO      →  {PIO}')
    print(f'Firmware →  {FW_ROOT}')
    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)

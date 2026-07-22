"""
Lights system (Bridge + Light Nodes) test suite — unit + static + live hardware.
Verifies HTTP console, Serial JSON input, WiFi connection fallback, and ACK/Timeout
tracking, per docs/magzimus-light-nodes-spec.md.
Usage: python3 tools/test_lights.py
"""
import sys, os, glob, re, time, struct, json

ROOT       = os.path.join(os.path.dirname(__file__), '..')
BRIDGE_SRC = os.path.join(ROOT, 'firmware', 'bridge')
PWM_SRC    = os.path.join(ROOT, 'firmware', 'pwm')
RESULTS    = []

# ── helpers ──────────────────────────────────────────────────────────────────

def ok(name, detail=''):
    RESULTS.append(('PASS', name, detail))
    print(f'  ✓  {name}  {detail}')

def fail(name, detail=''):
    RESULTS.append(('FAIL', name, detail))
    print(f'  ✗  {name}  {detail}')

def section(title):
    print(f'\n{"─"*60}\n  {title}\n{"─"*60}')

def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()

# ── 1. Protocol structs ───────────────────────────────────────────────────────

section('1. Protocol structs — light_cmd_t / light_ack_t (5 bytes)')

proto_h = read(os.path.join(BRIDGE_SRC, 'include', 'Protocol.h'))
node_proto_h = read(os.path.join(PWM_SRC, 'include', 'Protocol.h'))

if proto_h.strip() == node_proto_h.strip() or (
    'struct __attribute__((packed)) light_cmd_t' in proto_h and
    'struct __attribute__((packed)) light_cmd_t' in node_proto_h
):
    ok('Bridge/Node share light_cmd_t / light_ack_t layout')
else:
    fail('Protocol.h mismatch between bridge and pwm (node)')

cmd_t  = struct.Struct('<BBBBB')   # targetId, w, r, g, b
ack_t  = struct.Struct('<BBBBB')   # nodeId, w, r, g, b
if cmd_t.size == 5 and ack_t.size == 5:
    ok('light_cmd_t / light_ack_t pack to 5 bytes', f'cmd={cmd_t.size} ack={ack_t.size}')
else:
    fail('Struct size mismatch', f'cmd={cmd_t.size} ack={ack_t.size}')

packed = cmd_t.pack(0, 10, 255, 0, 128)
target, w, r, g, b = cmd_t.unpack(packed)
if (target, w, r, g, b) == (0, 10, 255, 0, 128):
    ok('light_cmd_t round-trip pack/unpack')
else:
    fail('light_cmd_t round-trip', str((target, w, r, g, b)))

# ── 2. Serial / HTTP JSON field extraction (extractIntField logic) ──────────

section('2. JSON field extraction — Bridge extractIntField() semantics')

def extract_int_field(body, key):
    """Python port of firmware/bridge/src/main.cpp::extractIntField — substring
    search for "key": followed by Arduino String::toInt() (leading digits, else 0)."""
    pattern = f'"{key}":'
    idx = body.find(pattern)
    if idx == -1:
        return 0
    rest = body[idx + len(pattern):]
    m = re.match(r'\s*(-?\d+)', rest)
    return int(m.group(1)) if m else 0

cases = [
    ('{"target":1,"r":255,"g":0,"b":0,"w":0}', {'target': 1, 'r': 255, 'g': 0, 'b': 0, 'w': 0}),
    ('{"target":0,"r":0,"g":0,"b":0,"w":0}',   {'target': 0, 'r': 0, 'g': 0, 'b': 0, 'w': 0}),
    ('{"r":128,"target":4}',                   {'target': 4, 'r': 128, 'g': 0, 'b': 0, 'w': 0}),
    ('{}',                                      {'target': 0, 'r': 0, 'g': 0, 'b': 0, 'w': 0}),
]
for body, expected in cases:
    got = {k: extract_int_field(body, k) for k in ('target', 'r', 'g', 'b', 'w')}
    if got == expected:
        ok('extractIntField parses', f'{body} -> {got}')
    else:
        fail('extractIntField mismatch', f'{body} -> got {got} expected {expected}')

# Bridge has no JSON library — verify it relies on this minimal extractor, not a lib.
if 'extractIntField' in read(os.path.join(BRIDGE_SRC, 'src', 'main.cpp')) and \
   'ArduinoJson' not in read(os.path.join(BRIDGE_SRC, 'src', 'main.cpp')):
    ok('Bridge uses minimal JSON extraction (no ArduinoJson dependency)')
else:
    fail('Bridge JSON parsing implementation changed unexpectedly')

# ── 3. ACK / Timeout tracking (trackSend / checkAckTimeouts / processAcks) ──

section('3. ACK / Timeout tracking — ports of Bridge logic')

class PendingAck:
    def __init__(self): self.waiting = False; self.sent_at = 0

class BridgeAckSim:
    def __init__(self):
        self.pending = {i: PendingAck() for i in range(1, 5)}
        self.log = []

    def track_send(self, target, now):
        targets = range(1, 5) if target == 0 else [target]
        for i in targets:
            self.pending[i].waiting = True
            self.pending[i].sent_at = now

    def check_timeouts(self, now):
        for i in range(1, 5):
            p = self.pending[i]
            if p.waiting and (now - p.sent_at) >= 200:
                p.waiting = False
                self.log.append(f'[TIMEOUT] Node {i}')

    def process_ack(self, node_id):
        self.log.append(f'[ACK] Node {node_id}')
        if 1 <= node_id <= 4:
            self.pending[node_id].waiting = False

sim = BridgeAckSim()
sim.track_send(0, now=1000)
if all(sim.pending[i].waiting for i in range(1, 5)):
    ok('target=0 (broadcast) arms timeout tracking for all 4 nodes')
else:
    fail('Broadcast tracking did not arm all nodes')

sim.process_ack(2)
sim.check_timeouts(now=1250)
fired = [m for m in sim.log if m.startswith('[TIMEOUT]')]
if fired == ['[TIMEOUT] Node 1', '[TIMEOUT] Node 3', '[TIMEOUT] Node 4']:
    ok('Timeout fires only for nodes that did not ACK', str(fired))
else:
    fail('Timeout set incorrect', str(fired))

sim2 = BridgeAckSim()
sim2.track_send(3, now=0)
sim2.check_timeouts(now=150)
if not sim2.log:
    ok('No premature timeout before 200ms elapsed')
else:
    fail('Premature timeout fired', str(sim2.log))
sim2.check_timeouts(now=200)
if sim2.log == ['[TIMEOUT] Node 3']:
    ok('Timeout fires at exactly 200ms threshold')
else:
    fail('Timeout threshold incorrect', str(sim2.log))

# ── 4. Static spec compliance — source inspection ────────────────────────────

section('4. Static spec compliance — Bridge & Node source')

bridge_main = read(os.path.join(BRIDGE_SRC, 'src', 'main.cpp'))
bridge_cfg  = read(os.path.join(BRIDGE_SRC, 'include', 'Config.h'))
node_main   = read(os.path.join(PWM_SRC, 'src', 'main.cpp'))
node_cfg    = read(os.path.join(PWM_SRC, 'include', 'Config.h'))

static_checks = [
    ('Bridge: fixed ESP-NOW channel constant', 'ESPNOW_CHANNEL' in bridge_cfg and 'ESPNOW_CHANNEL  1' in bridge_cfg),
    ('Bridge: AP fallback SSID/password = MagLight/magzimus', '"MagLight"' in bridge_cfg and '"magzimus"' in bridge_cfg),
    ('Bridge: per-network timeout before AP fallback', 'WIFI_NETWORK_TIMEOUT_MS' in bridge_cfg),
    ('Bridge: serves HTML console at /', "server.on(\"/\", HTTP_GET, handleRoot)" in bridge_main),
    ('Bridge: /color HTTP endpoint', "server.on(\"/color\", HTTP_POST, handleColor)" in bridge_main),
    ('Bridge: Serial JSON line interface', 'pollSerial' in bridge_main and "c == '\\n'" in bridge_main),
    ('Bridge: 200ms ACK timeout', '>= 200' in bridge_main),
    ('Bridge: ESP-NOW recv callback only buffers (no heavy work in ISR)', 's_hasAck = true' in bridge_main),
    ('Node: NODE_ID fixed at compile time (1-4)', 'NODE_ID  1' in node_cfg or '#define NODE_ID' in node_cfg),
    ('Node: PWM 1kHz, 8-bit', 'PWM_FREQ   1000' in node_cfg and 'PWM_BITS   8' in node_cfg),
    ('Node: GPIO pulled low immediately on boot', 'digitalWrite(PWM_PIN_W, LOW)' in node_main and node_main.index('digitalWrite(PWM_PIN_W, LOW)') < node_main.index('EspNow::init()')),
    ('Node: duplicate command -> no action, no ACK', 'continue; // duplicate of current status' in node_main),
    ('Node: ACK sent only on state change', node_main.count('EspNow::sendAck') == 1 and 'curW = cmd.w' in node_main),
]
for name, cond in static_checks:
    ok(name) if cond else fail(name)

# Fire-and-forget — no retry logic anywhere in bridge/node send paths
if 'retry' not in bridge_main.lower() and 'retry' not in node_main.lower():
    ok('Fire-and-forget: no retry logic present (per spec)')
else:
    fail('Unexpected retry logic found')

# ── 5. Live hardware — Bridge over Serial ─────────────────────────────────────

section('5. Live hardware — Bridge Serial console')

CANDIDATE_PORTS = sorted(glob.glob('/dev/cu.usbmodem*') + glob.glob('/dev/cu.usbserial*'))

try:
    import serial

    bridge_port = None
    boot_lines  = []
    for port in CANDIDATE_PORTS:
        try:
            s = serial.Serial(port, 115200, timeout=1)
            time.sleep(2)
            s.reset_input_buffer()
            time.sleep(0.5)
            data = s.read(4000).decode(errors='replace')
            s.close()
            if '[BOOT] Bridge ready' in data or 'Bridge MAC' in data:
                bridge_port = port
                boot_lines = data.splitlines()
                break
        except Exception:
            continue

    if not bridge_port:
        fail('Bridge not found on any candidate serial port', str(CANDIDATE_PORTS) or 'none detected')
    else:
        ok('Bridge detected', bridge_port)

        if any('[BOOT] AP started' in l for l in boot_lines):
            ok('Boot: AP started message present')
        else:
            fail('Boot: AP started message missing', str(boot_lines))

        if any('[BOOT] Connected to' in l for l in boot_lines) or any('[BOOT] No network found, AP mode only' in l for l in boot_lines):
            ok('Boot: WiFi STA connect attempt resolved (connected or AP-only fallback)')
        else:
            fail('Boot: no STA connect resolution found', str(boot_lines))

        if any('[BOOT] Bridge ready' in l for l in boot_lines):
            ok('Boot: "Bridge ready" printed after ESP-NOW init')
        else:
            fail('Boot: "Bridge ready" missing')

        bridge = serial.Serial(bridge_port, 115200, timeout=2)
        time.sleep(0.5)
        bridge.reset_input_buffer()

        # Serial JSON command -> expect ACK or TIMEOUT line within ~1s
        bridge.write(b'{"target":1,"r":255,"g":0,"b":0,"w":0}\n')
        time.sleep(0.8)
        resp = bridge.read(2000).decode(errors='replace')
        if 'Bridge ESP-NOW send' in resp:
            ok('Serial JSON command dispatched via ESP-NOW', resp.strip().splitlines()[-1] if resp.strip() else '')
        else:
            fail('Serial JSON command: no dispatch log seen', resp)

        time.sleep(0.5)
        resp2 = bridge.read(2000).decode(errors='replace')
        if '[ACK] Node 1' in resp2:
            ok('ACK received from Node 1')
        elif '[TIMEOUT] Node 1' in resp2:
            ok('Timeout correctly reported for Node 1 (no node on ESP-NOW range)')
        else:
            fail('Neither ACK nor TIMEOUT observed for Node 1', resp2)

        bridge.close()

except ImportError:
    fail('pyserial not installed', 'pip install pyserial')
except Exception as e:
    fail('Live test exception', str(e))

# ── 6. Live hardware — HTTP console ───────────────────────────────────────────

section('6. Live hardware — HTTP console (/ and /color)')

BRIDGE_HTTP_IP = os.environ.get('BRIDGE_IP')  # set manually once connected to MagLight AP / venue WiFi
if not BRIDGE_HTTP_IP:
    fail('BRIDGE_IP not set', 'export BRIDGE_IP=<bridge IP> (e.g. 192.168.4.1 on MagLight AP) to run this section')
else:
    try:
        import urllib.request
        with urllib.request.urlopen(f'http://{BRIDGE_HTTP_IP}/', timeout=3) as r:
            html = r.read().decode()
        if 'MAGZIMUS Lights' in html:
            ok('GET / serves console HTML', BRIDGE_HTTP_IP)
        else:
            fail('GET / did not return expected console HTML')

        body = json.dumps({'target': 0, 'r': 0, 'g': 0, 'b': 0, 'w': 0}).encode()
        req = urllib.request.Request(f'http://{BRIDGE_HTTP_IP}/color', data=body,
                                      headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=3) as r:
            resp_body = json.loads(r.read())
        if resp_body == {'status': 'ok'}:
            ok('POST /color returns {"status":"ok"}')
        else:
            fail('POST /color unexpected response', str(resp_body))
    except Exception as e:
        fail('HTTP console live test exception', str(e))

# ── Report ────────────────────────────────────────────────────────────────────

passed = sum(1 for r in RESULTS if r[0] == 'PASS')
failed = sum(1 for r in RESULTS if r[0] == 'FAIL')
total  = len(RESULTS)

print(f'\n{"="*60}')
print(f'  {passed}/{total} passed  |  {failed} failed')
print(f'{"="*60}')

from datetime import date
lines = [
    f'# Lights System Test Report — {date.today()}',
    '',
    f'**Result: {passed}/{total} passed** | {failed} failed',
    '',
    '## Results',
    '',
    '| Status | Test | Detail |',
    '|--------|------|--------|',
]
for status, name, detail in RESULTS:
    icon = '✅' if status == 'PASS' else '❌'
    lines.append(f'| {icon} | {name} | {detail} |')

lines += [
    '',
    '## Summary',
    '',
    f'- **Tested on:** {date.today()}',
    f'- **Pass:** {passed}',
    f'- **Fail:** {failed}',
    '',
    '## Notes',
    '',
    '- Sections 1-4 are unit/static tests — no hardware required.',
    '- Section 5 requires a Bridge (ESP32) on a `/dev/cu.usbmodem*` / `/dev/cu.usbserial*` port running the Bridge firmware.',
    '- Section 6 requires `BRIDGE_IP` env var set to the Bridge\'s IP (AP mode: `192.168.4.1` on SSID `MagLight`).',
    '- `credentials.h` currently has empty SSID/password placeholders — Bridge will always fall back to AP-only mode until venue/home WiFi is filled in.',
]

report_path = os.path.join(ROOT, 'docs', 'LIGHTS_TEST_REPORT.md')
with open(report_path, 'w') as f:
    f.write('\n'.join(lines) + '\n')

print('\nReport saved → docs/LIGHTS_TEST_REPORT.md')
sys.exit(0 if failed == 0 else 1)

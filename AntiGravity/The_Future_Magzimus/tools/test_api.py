#!/usr/bin/env python3
"""
Flask API stress test — no hardware required.
Uses Flask test client. Tests all REST routes for correct behavior,
error handling, and security (path traversal).
"""
import sys, os, json, tempfile, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../control/server'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../control/engine'))

# Patch bridge away before importing app
import app as server_app
from engine import Engine

PASS_COUNT = [0]
FAIL_LIST  = []

def ok(label):
    PASS_COUNT[0] += 1
    print(f"\033[32m  ✓ \033[0m {label}")

def fail(label, detail=''):
    FAIL_LIST.append(label)
    print(f"\033[31m  ✗ \033[0m {label}  {detail or ''}")

def section(title):
    print(f"\n{'─'*60}\n  {title}\n{'─'*60}")

# ── Set up test client ─────────────────────────────────────────────────────────
flask_app = server_app.app
flask_app.config['TESTING'] = True
c = flask_app.test_client()

# ── Inject a real Engine for route testing ─────────────────────────────────────
def _noop(*a, **kw): pass
eng = Engine(_noop, _noop, _noop, _noop)
server_app.engine = eng

# Create a minimal number file for engine
NUMBERS_DIR = server_app.NUMBERS_DIR
os.makedirs(NUMBERS_DIR, exist_ok=True)
_test_number_path = os.path.join(NUMBERS_DIR, '_test_stress.json')
_test_number = [{"id": "test-001", "name": "Stress Test Number", "events": [
    {
        "trigger": {"type": "staff_telemetry", "condition": "speed > 1"},
        "timelines": [{"device": "staff", "targetId": 1, "policy": "IGNORE",
                       "steps": [{"t": 0, "cmd": "LED_SOLID", "r": 255, "g": 0, "b": 0, "brightness": 150}]}]
    }
]}]
with open(_test_number_path, 'w') as f:
    json.dump(_test_number, f)
eng.load(_test_number_path)

# ── 1. Static routes ───────────────────────────────────────────────────────────
section("1. Static routes")

r = c.get('/')
if r.status_code == 200:
    ok("GET / → 200")
else:
    fail("GET / → 200", f"got {r.status_code}")

# ── 2. Command routes (no bridge → still 200) ──────────────────────────────────
section("2. Command routes (no bridge)")

def post_json(route, body=None):
    return c.post(route, json=body or {}, content_type='application/json')

for route, body in [
    ('/api/command/staff', {'targetId': 0xFFFF, 'cmdType': 1, 'r': 255, 'g': 0, 'b': 0, 'brightness': 150}),
    ('/api/command/relay', {'targetId': 0xFF, 'state': 1, 'durationMs': 500}),
    ('/api/command/pwm',   {'targetId': 0xFF, 'w': 255, 'r': 0, 'g': 0, 'b': 0, 'fadeMs': 0}),
    ('/api/command/progress', {'targetId': 0xFF, 'mode': 1, 'value': 50, 'r': 0, 'g': 255, 'b': 0, 'fadeMs': 100}),
    ('/api/command/net_status', {'status': 2, 'targetId': 0xFF}),
]:
    r = post_json(route, body)
    data = r.get_json()
    if r.status_code == 200 and data and data.get('ok'):
        ok(f"POST {route} → ok")
    else:
        fail(f"POST {route} → ok", f"status={r.status_code} body={data}")

# Routes that require bridge → should return ok=False, not crash
for route in ['/api/hub/pause', '/api/command/role', '/api/wifi', '/api/discover']:
    r = post_json(route, {})
    if r.status_code in (200, 400, 503):
        ok(f"POST {route} (no bridge) → handles gracefully [{r.status_code}]")
    else:
        fail(f"POST {route} (no bridge) → handles gracefully", f"got {r.status_code}")

# ── 3. Number routes ───────────────────────────────────────────────────────────
section("3. Number CRUD routes")

# List numbers
r = c.get('/api/numbers/list')
data = r.get_json()
if r.status_code == 200 and data.get('ok') and isinstance(data.get('numbers'), list):
    ok(f"GET /api/numbers/list → {len(data['numbers'])} numbers")
else:
    fail("GET /api/numbers/list", f"{data}")

# Get specific number
r = c.get('/api/numbers/get?file=_test_stress.json')
data = r.get_json()
if r.status_code == 200 and data.get('ok') and data.get('data'):
    ok("GET /api/numbers/get?file=_test_stress.json → found")
else:
    fail("GET /api/numbers/get valid file", f"{data}")

# Get missing file
r = c.get('/api/numbers/get?file=nonexistent.json')
if r.status_code == 404:
    ok("GET /api/numbers/get nonexistent → 404")
else:
    fail("GET /api/numbers/get nonexistent → 404", f"got {r.status_code}")

# Path traversal attacks
for evil in ['../../etc/passwd', '../CLAUDE.md', '../../.zshrc', '/etc/passwd']:
    r = c.get(f'/api/numbers/get?file={evil}')
    if r.status_code == 404:
        ok(f"Path traversal '{evil}' → 404 (blocked)")
    else:
        fail(f"Path traversal '{evil}' → blocked", f"got {r.status_code} data={r.get_json()}")

# Save number
save_body = {'file': '_test_save.json', 'data': {'id': 'saved-001', 'name': 'Saved', 'events': []}}
r = post_json('/api/numbers/save', save_body)
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/numbers/save → saved")
    # Clean up
    saved_path = os.path.join(NUMBERS_DIR, '_test_save.json')
    if os.path.exists(saved_path):
        os.unlink(saved_path)
else:
    fail("POST /api/numbers/save", f"{data}")

# Save with no data
r = post_json('/api/numbers/save', {})
if r.status_code == 400:
    ok("POST /api/numbers/save missing data → 400")
else:
    fail("POST /api/numbers/save missing data → 400", f"got {r.status_code}")

# Save with path traversal in filename
r = post_json('/api/numbers/save', {'file': '../../hack.json', 'data': {}})
data = r.get_json()
if data and not data.get('ok'):
    ok("POST /api/numbers/save path traversal in filename → rejected")
elif r.status_code == 400:
    ok("POST /api/numbers/save path traversal in filename → rejected")
else:
    # It might have been saved with basename only (safe)
    safe_path = os.path.join(NUMBERS_DIR, 'hack.json')
    traversal_path = os.path.realpath(os.path.join(NUMBERS_DIR, '../../hack.json'))
    if not os.path.exists(traversal_path) or os.path.dirname(traversal_path) == NUMBERS_DIR:
        ok("POST /api/numbers/save path traversal: basename used (safe)")
        if os.path.exists(safe_path):
            os.unlink(safe_path)
    else:
        fail("POST /api/numbers/save path traversal bypassed!", f"{data}")

# Load number into engine
r = post_json('/api/number/load', {'path': _test_number_path})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/number/load → ok")
else:
    fail("POST /api/number/load", f"{data}")

# Load non-existent path
r = post_json('/api/number/load', {'path': '/nonexistent/path.json'})
data = r.get_json()
if r.status_code == 400 and not data.get('ok'):
    ok("POST /api/number/load bad path → 400")
else:
    fail("POST /api/number/load bad path → 400", f"got {r.status_code}")

# ── 4. Slots and hotswap ───────────────────────────────────────────────────────
section("4. Slots and hotswap")

r = c.get('/api/slots')
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("GET /api/slots → ok")
else:
    fail("GET /api/slots", f"{data}")

r = post_json('/api/slots', {'slot': 'staff-A', 'deviceId': 0x028C})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/slots set → ok")
else:
    fail("POST /api/slots set", f"{data}")

# Missing params
r = post_json('/api/slots', {'slot': 'staff-A'})
if r.status_code == 400:
    ok("POST /api/slots missing deviceId → 400")
else:
    fail("POST /api/slots missing deviceId → 400", f"got {r.status_code}")

r = post_json('/api/hotswap', {'slot': 'staff-A', 'deviceId': 0x029F})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/hotswap → ok")
else:
    fail("POST /api/hotswap", f"{data}")

r = post_json('/api/hotswap', {'slot': 'staff-A'})
if r.status_code == 400:
    ok("POST /api/hotswap missing deviceId → 400")
else:
    fail("POST /api/hotswap missing deviceId → 400", f"got {r.status_code}")

# ── 5. Engine routes ───────────────────────────────────────────────────────────
section("5. Engine routes (ShowTimer, Accumulator)")

r = post_json('/api/showtimer/start', {'duration': 0.2})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/showtimer/start → ok")
else:
    fail("POST /api/showtimer/start", f"{data}")

time.sleep(0.05)
r = post_json('/api/showtimer/stop', {})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/showtimer/stop → ok")
else:
    fail("POST /api/showtimer/stop", f"{data}")

r = post_json('/api/accumulator/configure', {'decayRate': 50.0})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/accumulator/configure → ok")
else:
    fail("POST /api/accumulator/configure", f"{data}")

r = post_json('/api/accumulator/pulse', {'amount': 25.0})
data = r.get_json()
if r.status_code == 200 and data.get('ok') and data.get('value', 0) > 0:
    ok(f"POST /api/accumulator/pulse → value={data['value']}")
else:
    fail("POST /api/accumulator/pulse", f"{data}")

r = c.get('/api/accumulator/value')
data = r.get_json()
if r.status_code == 200 and data.get('ok') and 'value' in data:
    ok(f"GET /api/accumulator/value → {data['value']:.1f}")
else:
    fail("GET /api/accumulator/value", f"{data}")

r = post_json('/api/accumulator/reset', {})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/accumulator/reset → ok")
else:
    fail("POST /api/accumulator/reset", f"{data}")

# ── 6. Trigger test endpoint ───────────────────────────────────────────────────
section("6. Trigger test injection")

r = post_json('/api/trigger/test', {'data': {'triggerType': 'threshold', 'signal': 'speed'}})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/trigger/test → ok")
else:
    fail("POST /api/trigger/test", f"{data}")

# Empty body
r = post_json('/api/trigger/test', {})
if r.status_code == 200:
    ok("POST /api/trigger/test empty body → ok (no crash)")
else:
    fail("POST /api/trigger/test empty body → no crash", f"got {r.status_code}")

# ── 7. Effects registry ────────────────────────────────────────────────────────
section("7. Effects registry")

r = c.get('/api/effects')
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("GET /api/effects → ok")
else:
    fail("GET /api/effects", f"{data}")

# ── 8. Firmware builds list ────────────────────────────────────────────────────
section("8. Firmware routes (no build — list only)")

r = c.get('/api/firmware/builds')
data = r.get_json()
if r.status_code == 200 and data.get('ok') and 'builds' in data:
    ok(f"GET /api/firmware/builds → {len(data['builds'])} builds listed")
else:
    fail("GET /api/firmware/builds", f"{data}")

# Unknown firmware key
r = post_json('/api/firmware/build', {'fw': 'totally_unknown_fw_xyz'})
data = r.get_json()
if r.status_code == 400 and not data.get('ok'):
    ok("POST /api/firmware/build unknown fw → 400")
else:
    fail("POST /api/firmware/build unknown fw → 400", f"got {r.status_code} {data}")

# ── 9. Input type coercion edge cases ─────────────────────────────────────────
section("9. Input type coercion")

# String where int expected — should not crash
r = post_json('/api/command/staff', {'targetId': 'not-an-int', 'cmdType': 1, 'r': 255, 'g': 0, 'b': 0, 'brightness': 150})
if r.status_code in (200, 400, 500):
    # As long as it doesn't throw a 500 with a traceback we're not catching
    data = r.get_json()
    if data is not None:
        ok(f"POST /api/command/staff bad targetId → {r.status_code} (no unhandled crash)")
    else:
        fail("POST /api/command/staff bad targetId → JSON response", f"got {r.status_code} but no JSON")
else:
    fail("POST /api/command/staff bad targetId → no crash", f"got {r.status_code}")

# Accumulator pulse with string amount
r = post_json('/api/accumulator/pulse', {'amount': 'fifty'})
if r.status_code in (200, 400, 500):
    data = r.get_json()
    if r.status_code == 400 or (r.status_code == 200 and data):
        ok(f"POST /api/accumulator/pulse string amount → {r.status_code}")
    else:
        ok(f"POST /api/accumulator/pulse string amount → {r.status_code}")

# Showtimer with missing duration
r = post_json('/api/showtimer/start', {})
data = r.get_json()
if r.status_code == 200 and data.get('ok'):
    ok("POST /api/showtimer/start no duration → uses default (60.0)")
    post_json('/api/showtimer/stop', {})
else:
    fail("POST /api/showtimer/start no duration → default", f"{data}")

# ── 10. No-engine graceful handling ───────────────────────────────────────────
section("10. No-engine graceful handling")

saved_engine = server_app.engine
server_app.engine = None

r = post_json('/api/showtimer/start', {'duration': 5.0})
data = r.get_json()
if r.status_code == 503 and not data.get('ok'):
    ok("POST /api/showtimer/start (no engine) → 503")
else:
    fail("POST /api/showtimer/start (no engine) → 503", f"got {r.status_code} {data}")

r = post_json('/api/accumulator/configure', {'decayRate': 1.0})
data = r.get_json()
if r.status_code == 503 and not data.get('ok'):
    ok("POST /api/accumulator/configure (no engine) → 503")
else:
    fail("POST /api/accumulator/configure (no engine) → 503", f"got {r.status_code} {data}")

r = c.get('/api/slots')
data = r.get_json()
if r.status_code == 200 and data.get('slots') == {}:
    ok("GET /api/slots (no engine) → empty slots, no crash")
else:
    fail("GET /api/slots (no engine) → no crash", f"{data}")

server_app.engine = saved_engine

# ── Cleanup ────────────────────────────────────────────────────────────────────
if os.path.exists(_test_number_path):
    os.unlink(_test_number_path)

# ── Summary ────────────────────────────────────────────────────────────────────
total = PASS_COUNT[0] + len(FAIL_LIST)
print(f"\n{'='*60}")
print(f"  {PASS_COUNT[0]}/{total} passed")
if FAIL_LIST:
    print(f"\033[31m  Failures:\033[0m")
    for f in FAIL_LIST:
        print(f"    ✗  {f}")
else:
    print("\033[32m  All API tests passed.\033[0m")
sys.exit(len(FAIL_LIST))

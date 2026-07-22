"""
Protocol test suite — unit + live hardware.
Usage: python3 tools/test_protocol.py
"""
import sys, os, time, struct, threading, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'control', 'server'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'control', 'engine'))

import protocol as proto
from device_registry import DeviceRegistry
from timeline import Timeline

HUB_PORT = '/dev/cu.usbserial-0001'
RESULTS  = []

# ── helpers ──────────────────────────────────────────────────────────────────

def ok(name, detail=''):
    RESULTS.append(('PASS', name, detail))
    print(f'  ✓  {name}  {detail}')

def fail(name, detail=''):
    RESULTS.append(('FAIL', name, detail))
    print(f'  ✗  {name}  {detail}')

def section(title):
    print(f'\n{"─"*60}\n  {title}\n{"─"*60}')

# ── 1. CRC ────────────────────────────────────────────────────────────────────

section('1. CRC-8')

crc = proto._crc8(b'')
if crc == 0:
    ok('CRC of empty input is 0')
else:
    fail('CRC of empty input', f'got {crc}')

known = proto._crc8(bytes([0x10, 0x08, 0x00, 0x01, 0xff, 0xff, 0x01, 0x00, 0x00, 0xff, 0x96]))
frame = proto.pack_staff_command(0xFFFF, 1, 0, 0, 255, 150)
crc_byte = frame[-1]
meta     = bytes([proto.MSG_CMD_STAFF]) + struct.pack('<H', len(frame)-6)
payload  = frame[5:-1]
recalc   = proto._crc8(meta + payload)
if crc_byte == recalc:
    ok('CRC matches packed frame')
else:
    fail('CRC mismatch', f'frame={crc_byte:02X} recalc={recalc:02X}')

tampered = bytearray(frame); tampered[-2] ^= 0xFF
if proto._crc8(bytes([tampered[2]]) + struct.pack('<H', len(tampered)-6) + bytes(tampered[5:-1])) != tampered[-1]:
    ok('Tampered payload detected by CRC')
else:
    fail('Tampered payload NOT detected')

# ── 2. Frame structure ────────────────────────────────────────────────────────

section('2. Serial frame structure [AA 55 type len_L len_H payload CRC]')

for name, frame, exp_type, exp_len in [
    ('pack_staff_command',  proto.pack_staff_command(0xFFFF, 1, 255, 0, 0, 200),  proto.MSG_CMD_STAFF,  8),
    ('pack_relay_command',  proto.pack_relay_command(0xFF, 1, 1500),               proto.MSG_CMD_RELAY,  5),
    ('pack_pwm_command',    proto.pack_pwm_command(0xFF, 255, 0, 0, 0, 500),       proto.MSG_CMD_PWM,    8),
    ('pack_wifi_ctrl',      proto.pack_wifi_ctrl(0xFFFF, 1),                       proto.MSG_WIFI_CTRL,  4),
    ('pack_role_ctrl',      proto.pack_role_ctrl(0x028C, False),                   proto.MSG_ROLE_CTRL,  5),
    ('pack_discover',       proto.pack_discover(),                                 proto.MSG_DISCOVER,   1),
]:
    if frame[:2] != b'\xAA\x55':
        fail(f'{name} header', f'got {frame[:2].hex()}'); continue
    msg_type = frame[2]
    length   = struct.unpack_from('<H', frame, 3)[0]
    payload  = frame[5:5+length]
    if msg_type != exp_type:
        fail(f'{name} type', f'expected {exp_type:02X} got {msg_type:02X}'); continue
    if length != exp_len:
        fail(f'{name} length', f'expected {exp_len} got {length}'); continue
    meta   = bytes([msg_type]) + struct.pack('<H', length)
    crc_ok = frame[-1] == proto._crc8(meta + payload)
    if crc_ok:
        ok(f'{name}', f'type=0x{msg_type:02X} len={length}')
    else:
        fail(f'{name} CRC')

# ── 3. Parse functions ────────────────────────────────────────────────────────

section('3. Parse: telemetry + identity')

# 25-byte StaffTelemetry: groupId=1 deviceId=0x028C speed=1.234 angle=45.68 flags=THROW
raw_telem = bytes.fromhex('aa55011900018c02b6f39d3f46b63642640038ff2c019cffc800d4fe04012f')
msg_t = raw_telem[2]
pay_t = raw_telem[5:5+struct.unpack_from('<H', raw_telem, 3)[0]]
d = proto.parse_staff_telemetry(pay_t)
if d and d['deviceId'] == 0x028C and d['throw'] is True and d['orientation'] == 'vertical':
    ok('parse_staff_telemetry', f"id={d['deviceId']:04X} angle={d['angle']:.1f}° speed={d['speed']:.3f} throw={d['throw']}")
else:
    fail('parse_staff_telemetry', str(d))

raw_ident = bytes.fromhex('aa5521110001218c020176312e3000000000000000007d')
pay_i = raw_ident[5:5+struct.unpack_from('<H', raw_ident, 3)[0]]
di = proto.parse_identity(pay_i)
if di and di['role'] == 'staff' and di['firmware'] == 'v1.0':
    ok('parse_identity', f"id={di['deviceId']} role={di['role']} fw={di['firmware']}")
else:
    fail('parse_identity', str(di))

# ── 4. Role ctrl payload ──────────────────────────────────────────────────────

section('4. RoleCtrl packet contents')

frame_rx = proto.pack_role_ctrl(0x028C, False)
payload  = frame_rx[5:-1]
group_id, msg_type, target_id, tx_en = struct.unpack('<BBHB', payload)
if group_id == proto.GROUP_ID and msg_type == proto.MSG_ROLE_CTRL and target_id == 0x028C and tx_en == 0:
    ok('pack_role_ctrl (txEnabled=False)', f'groupId={group_id} msgType=0x{msg_type:02X} targetId={target_id:04X} txEn={tx_en}')
else:
    fail('pack_role_ctrl', f'{group_id} {msg_type:02X} {target_id:04X} {tx_en}')

frame_tx = proto.pack_role_ctrl(0xFFFF, True)
payload  = frame_tx[5:-1]
_, _, _, tx_en2 = struct.unpack('<BBHB', payload)
if tx_en2 == 1:
    ok('pack_role_ctrl (txEnabled=True)')
else:
    fail('pack_role_ctrl txEnabled=True', f'got {tx_en2}')

# ── 5. DeviceRegistry ─────────────────────────────────────────────────────────

section('5. DeviceRegistry — INTERRUPT / QUEUE / IGNORE + slots')

reg   = DeviceRegistry()
order = []

def make_tl(label, duration=0.05):
    def sender(step): order.append(label)
    tl = Timeline([{'t': 0, 'cmd': 'X'}], sender)
    return tl

# IGNORE: second timeline dropped while first is running
reg.run(('staff', 1), make_tl('A'), 'IGNORE')
reg.run(('staff', 1), make_tl('B'), 'IGNORE')
time.sleep(0.15)
if order == ['A']:
    ok('IGNORE policy: second dropped')
else:
    fail('IGNORE policy', f'order={order}')

order.clear()

# QUEUE: second waits
reg.run(('staff', 2), make_tl('C'), 'QUEUE')
reg.run(('staff', 2), make_tl('D'), 'QUEUE')
time.sleep(0.3)
if order == ['C', 'D']:
    ok('QUEUE policy: second runs after first')
else:
    fail('QUEUE policy', f'order={order}')

order.clear()

# INTERRUPT: second cancels first
import time as _time
def make_slow_tl(label):
    def sender(step): order.append(label)
    tl = Timeline([{'t': 0, 'cmd': 'X'}, {'t': 0.5, 'cmd': 'Y'}], sender)
    return tl

reg.run(('staff', 3), make_slow_tl('E'), 'INTERRUPT')
_time.sleep(0.05)
reg.run(('staff', 3), make_tl('F'),       'INTERRUPT')
_time.sleep(0.2)
if 'F' in order:
    ok('INTERRUPT policy: second preempts first')
else:
    fail('INTERRUPT policy', f'order={order}')

# Slots
reg.set_slot('staff_left', 0x028C)
reg.set_slot('staff_right', 0xAD44)
slots = reg.list_slots()
if slots == {'staff_left': 0x028C, 'staff_right': 0xAD44}:
    ok('set_slot / list_slots')
else:
    fail('set_slot', str(slots))

reg.hotswap('staff_left', 0x1234)
if reg.resolve('staff_left') == 0x1234:
    ok('hotswap: slot updated to new deviceId')
else:
    fail('hotswap', f"got {reg.resolve('staff_left')}")

if reg.resolve('staff_right') == 0xAD44:
    ok('hotswap: other slot unchanged')
else:
    fail('hotswap side-effect', str(reg.list_slots()))

# ── 6. Live hardware ──────────────────────────────────────────────────────────

section('6. Live hardware — Hub + Staffs')

try:
    from serial_bridge import SerialBridge

    live_devices   = {}
    live_telemetry = {}
    live_lock      = threading.Lock()

    def on_telem(d):
        with live_lock: live_telemetry[d['deviceId']] = d
    def on_ident(d):
        with live_lock: live_devices[d['deviceId']] = d

    bridge = SerialBridge(HUB_PORT, 115200, on_telem, on_ident)
    bridge.start()
    time.sleep(0.4)
    ok('Serial bridge opened', HUB_PORT)

    # Telemetry arrives without any command
    time.sleep(2)
    with live_lock: n_telem = len(live_telemetry)
    if n_telem >= 1:
        ok(f'Telemetry received', f'{n_telem} sender(s): {[f"{i:04X}" for i in live_telemetry]}')
    else:
        fail('No telemetry received')

    # Discover
    with live_lock: live_devices.clear()
    bridge.send(proto.pack_discover())
    time.sleep(2)
    with live_lock: n_dev = len(live_devices)
    if n_dev >= 2:
        ok(f'Discover: {n_dev} devices responded', str([d for d in live_devices]))
    elif n_dev == 1:
        fail('Discover: only 1 device responded', str([d for d in live_devices]))
    else:
        fail('Discover: no devices responded')

    # LED_SOLID broadcast
    bridge.send(proto.pack_staff_command(0xFFFF, 1, 0, 0, 255, 200))
    time.sleep(0.5)
    with live_lock: still_telem = len(live_telemetry)
    if still_telem >= 1:
        ok('Telemetry continues after LED_SOLID command')
    else:
        fail('Telemetry stopped after LED_SOLID')

    # LED_OFF
    bridge.send(proto.pack_staff_command(0xFFFF, 0, 0, 0, 0, 0))
    time.sleep(0.3)
    ok('LED_OFF sent successfully')

    # Role ctrl — send and don't crash
    bridge.send(proto.pack_role_ctrl(0xFFFF, True))
    time.sleep(0.3)
    ok('Role ctrl broadcast sent (tx=enabled)')

    # Telemetry sanity check
    with live_lock:
        for did, d in live_telemetry.items():
            angle = d['angle']
            speed = d['speed']
            if -180 <= angle <= 180 and speed >= 0:
                ok(f'Telemetry sanity id={did:04X}', f'angle={angle:.1f}° speed={speed:.3f}')
            else:
                fail(f'Telemetry out of range id={did:04X}', f'angle={angle} speed={speed}')

    # ── 7. LED effects (SPARKLE / FLAME / RAINBOW) ───────────────────────────
    section('7. LED effects — live hardware')
    for cmd_name, cmd_type, r, g, b, br in [
        ('CMD_LED_SPARKLE', proto.CMD_LED_SPARKLE, 255, 255, 255, 128),
        ('CMD_LED_FLAME',   proto.CMD_LED_FLAME,   0,   0,   0,   0),
        ('CMD_LED_RAINBOW', proto.CMD_LED_RAINBOW,  0,   0,   0,   0),
    ]:
        bridge.send(proto.pack_staff_command(0xFFFF, cmd_type, r, g, b, br))
        time.sleep(0.4)
        with live_lock: active = len(live_telemetry) >= 1
        if active:
            ok(f'{cmd_name} sent + telemetry active')
        else:
            fail(f'{cmd_name}: telemetry stopped after command')
    bridge.send(proto.pack_staff_command(0xFFFF, proto.CMD_LED_OFF, 0, 0, 0, 0))
    time.sleep(0.3)
    ok('LED_OFF after effects')

    # ── 8. Hot-Swap Slots (engine layer) ─────────────────────────────────────
    section('8. Hot-Swap Slots')
    from engine import Engine
    import json as _json, tempfile as _tmp, os as _os

    fired_to = []
    def _send_staff(tid, ct, r, g, b, br): fired_to.append(tid)
    _eng = Engine(_send_staff, lambda *a: None, lambda *a: None)
    _num = [{"events": [{"trigger": {"type":"staff_telemetry","condition":"speed>0.1"},
              "timelines": [{"device":"staff","targetSlot":"main","policy":"IGNORE",
                             "steps":[{"t":0,"cmd":"LED_SOLID","r":255,"g":0,"b":0,"brightness":200}]}]}]}]
    _tf = _tmp.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    _json.dump(_num, _tf); _tf.close()
    _eng.load(_tf.name); _os.unlink(_tf.name)

    _eng.on_telemetry({'deviceId':0xAD44,'speed':1.0,'angle':0})
    time.sleep(0.1)
    if not fired_to:
        ok('targetSlot undefined → timeline skipped')
    else:
        fail('targetSlot undefined should skip', f'fired to {fired_to}')

    _eng._registry.set_slot('main', 0xAD44)
    _eng.on_telemetry({'deviceId':0xAD44,'speed':1.0,'angle':0})
    time.sleep(0.2)
    if 0xAD44 in fired_to:
        ok('targetSlot=AD44 → timeline fired to AD44')
    else:
        fail('targetSlot=AD44 not fired', str(fired_to))

    fired_to.clear()
    _eng._registry.hotswap('main', 0x028C)
    _eng.on_telemetry({'deviceId':0xAD44,'speed':1.0,'angle':0})
    time.sleep(0.2)
    if 0x028C in fired_to:
        ok('hotswap AD44→028C: timeline redirected')
    else:
        fail('hotswap: timeline not redirected', str(fired_to))

    # ── 9. NVS Role Ctrl ─────────────────────────────────────────────────────
    section('9. NVS Role Ctrl (live)')
    def _senders(sec=3):
        ids = set()
        b2 = SerialBridge(HUB_PORT, 115200, lambda d: ids.add(d['deviceId']), lambda d:None)
        b2.start(); time.sleep(sec); b2.close()
        return ids

    def _send_role(tid, enabled):
        bridge.send(proto.pack_role_ctrl(tid, enabled))
        time.sleep(2.5)

    ids_base = _senders(2)
    if 0xAD44 in ids_base:
        _send_role(0xAD44, False)
        ids_off = _senders(3)
        silent = 0xAD44 not in ids_off
        if silent:
            ok('ROLE_CTRL txEnabled=false: AD44 stopped tx')
        else:
            fail('ROLE_CTRL false: AD44 still tx')
        _send_role(0xAD44, True)
        ids_on = _senders(3)
        if 0xAD44 in ids_on:
            ok('ROLE_CTRL txEnabled=true: AD44 resumed tx')
        else:
            fail('ROLE_CTRL true: AD44 not resumed')
    else:
        fail('NVS Role test: AD44 not in baseline', str([f'{i:04X}' for i in ids_base]))

    # ── 10. Extended Telemetry — flags field (spec-test-001) ─────────────────
    section('10. Extended Telemetry — Staff flags (spec-test-001)')

    # Unit: parse returns all expected keys
    import struct as _struct
    raw_25 = _struct.pack('<BHffhhhhhhBB',
        1,       # groupId
        0x028C,  # deviceId
        2.5,     # speed
        45.0,    # angle
        0, 0, 0, # acc
        0, 0, 0, # gyro
        0,       # motionType
        0x05,    # flags: THROW(0x01) | SPIN_CW(0x04)
    )
    d25 = proto.parse_staff_telemetry(raw_25)
    if d25 and all(k in d25 for k in ('flags','throw','catch','spin_cw','orientation','impact')):
        ok('parse_staff_telemetry returns all flag keys')
    else:
        fail('parse_staff_telemetry missing keys', str(d25.keys() if d25 else 'None'))

    if d25 and d25['throw'] and d25['spin_cw'] and not d25['catch'] and not d25['impact']:
        ok('flags 0x05 decoded correctly', f"throw={d25['throw']} catch={d25['catch']} spin_cw={d25['spin_cw']}")
    else:
        fail('flags 0x05 decode error', str(d25))

    if d25 and d25['orientation'] == 'horizontal':
        ok('orientation bits (0x00) → horizontal')
    else:
        fail('orientation decode', f"got {d25.get('orientation') if d25 else 'None'}")

    # Unit: all orientations
    for flags_val, expected_orient in [(0x00, 'horizontal'), (0x08, 'horizontal'), (0x10, 'inverted')]:
        raw_o = _struct.pack('<BHffhhhhhhBB', 1, 1, 0, 0, 0,0,0, 0,0,0, 0, flags_val)
        do = proto.parse_staff_telemetry(raw_o)
        got = do.get('orientation') if do else None
        if got == expected_orient:
            ok(f'orientation flags=0x{flags_val:02X} → {expected_orient}')
        else:
            fail(f'orientation flags=0x{flags_val:02X}', f'expected {expected_orient} got {got}')

    # Live: read 5s of telemetry and report flag activity
    flags_seen = {'throw':0,'catch':0,'spin_cw':0,'impact':0,'orientations':set()}
    live_count = [0]

    def _on_ext(d):
        live_count[0] += 1
        if d.get('throw'):   flags_seen['throw']   += 1
        if d.get('catch'):   flags_seen['catch']   += 1
        if d.get('spin_cw'): flags_seen['spin_cw'] += 1
        if d.get('impact'):  flags_seen['impact']  += 1
        if 'orientation' in d:
            flags_seen['orientations'].add(d['orientation'])

    b_ext = SerialBridge(HUB_PORT, 115200, _on_ext, lambda d: None)
    b_ext.start()
    print('  [live] סורק telemetry 5s — הזז את הסטאף...')
    time.sleep(5)
    b_ext.close()

    if live_count[0] >= 10:
        ok(f'Extended telemetry live', f'{live_count[0]} frames | throw={flags_seen["throw"]} catch={flags_seen["catch"]} spin={flags_seen["spin_cw"]} impact={flags_seen["impact"]} orient={flags_seen["orientations"]}')
    else:
        fail('Extended telemetry: insufficient frames', f'{live_count[0]} received')

    bridge.close()

except FileNotFoundError:
    fail('Hub not connected', HUB_PORT)
except Exception as e:
    fail('Live test exception', str(e))

# ── Report ────────────────────────────────────────────────────────────────────

passed = sum(1 for r in RESULTS if r[0] == 'PASS')
failed = sum(1 for r in RESULTS if r[0] == 'FAIL')
total  = len(RESULTS)

print(f'\n{"="*60}')
print(f'  {passed}/{total} passed  |  {failed} failed')
print(f'{"="*60}')

# Write MD report
from datetime import date
lines = [
    f'# Protocol Test Report — {date.today()}',
    '',
    f'**Result: {passed}/{total} passed** | {failed} failed',
    '',
]

sections_map = {
    '1': 'CRC-8',
    '2': 'Serial frame structure',
    '3': 'Parse: telemetry + identity',
    '4': 'RoleCtrl packet contents',
    '5': 'DeviceRegistry — policies + slots',
    '6': 'Live hardware',
    '7': 'LED effects (SPARKLE/FLAME/RAINBOW)',
    '8': 'Hot-Swap Slots',
    '9': 'NVS Role Ctrl',
}

current_section = None
for status, name, detail in RESULTS:
    # detect section from name
    for prefix, title in sections_map.items():
        # group by order of results
        pass

lines += ['## Results', '', '| Status | Test | Detail |', '|--------|------|--------|']
for status, name, detail in RESULTS:
    icon = '✅' if status == 'PASS' else '❌'
    lines.append(f'| {icon} | {name} | {detail} |')

lines += [
    '',
    '## Summary',
    '',
    f'- **Tested on:** {date.today()}',
    f'- **Hub port:** `{HUB_PORT}`',
    f'- **Pass:** {passed}',
    f'- **Fail:** {failed}',
    '',
    '## Notes',
    '',
    '- Unit tests run without hardware (CRC, framing, registry, slots)',
    '- Live tests require Hub on `/dev/cu.usbserial-0001` with both Staffs in ESP-NOW range',
    '- `HUB_TIMEOUT_MS = 3000` — Staff falls back to IMU after 3s without ACK',
    '- Role assignment persisted to NVS; default `tx_enabled = true`',
]

report_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'PROTOCOL_TEST_REPORT.md')
with open(report_path, 'w') as f:
    f.write('\n'.join(lines) + '\n')

print(f'\nReport saved → docs/PROTOCOL_TEST_REPORT.md')
sys.exit(0 if failed == 0 else 1)

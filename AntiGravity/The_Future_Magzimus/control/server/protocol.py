"""Serial framing protocol — mirrors firmware Protocol.h and SerialBridge.cpp."""
from __future__ import annotations
import struct

HEADER = b'\xAA\x55'

MSG_STAFF_TELEMETRY = 0x01
MSG_CMD_STAFF       = 0x10
MSG_CMD_RELAY       = 0x11
MSG_CMD_PWM         = 0x12
MSG_DISCOVER        = 0x20
MSG_IDENTITY        = 0x21
CMD_LED_OFF     = 0
CMD_LED_SOLID   = 1
CMD_LED_SPARKLE = 2
CMD_LED_FLAME   = 3
CMD_LED_RAINBOW = 4
CMD_LED_TILT    = 5
CMD_CALIBRATE   = 6

MSG_PAIR_REQ    = 0x40
MSG_PAIR_ACK    = 0x41
MSG_CALIBRATE   = 0x32
MSG_HUB_PAUSE   = 0x61
MSG_AUTONOMOUS  = 0x62

MSG_WIFI_CTRL       = 0x30
MSG_ROLE_CTRL       = 0x31

ROLES = {1: 'staff', 2: 'relay', 3: 'pwm'}

GROUP_ID = 1

# Struct formats (little-endian, packed — no padding)
# StaffTelemetry: groupId(B) deviceId(H) speed(f) angle(f) acc(3×h) gyro(3×h) motionType(B) = 24 bytes
_ST  = struct.Struct('<BHffhhhhhhB')
# HubCommand:    groupId(B) targetId(H) cmdType(B) r(B) g(B) b(B) brightness(B) = 8 bytes
_HC  = struct.Struct('<BHBBBBB')
# RelayCommand:  groupId(B) targetId(B) state(B) durationMs(H) = 5 bytes
_RC  = struct.Struct('<BBBH')
# PWMCommand:    groupId(B) targetId(B) w(B) r(B) g(B) b(B) fadeMs(H) = 8 bytes
_PWM = struct.Struct('<BBBBBBH')


def _crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) if (crc & 0x80) else (crc << 1)
        crc &= 0xFF
    return crc


def _frame(msg_type: int, payload: bytes) -> bytes:
    meta = bytes([msg_type]) + struct.pack('<H', len(payload))
    crc  = _crc8(meta + payload)
    return HEADER + meta + payload + bytes([crc])


# ─── Outgoing (Mac → Hub) ─────────────────────────────────────────────────────

def pack_staff_command(target_id: int, cmd_type: int,
                       r: int, g: int, b: int, brightness: int) -> bytes:
    payload = _HC.pack(GROUP_ID, target_id, cmd_type, r, g, b, brightness)
    return _frame(MSG_CMD_STAFF, payload)


def pack_relay_command(target_id: int, state: int, duration_ms: int = 0) -> bytes:
    payload = _RC.pack(GROUP_ID, target_id, state, duration_ms)
    return _frame(MSG_CMD_RELAY, payload)


def pack_pwm_command(target_id: int, w: int, r: int,
                     g: int, b: int, fade_ms: int = 0) -> bytes:
    payload = _PWM.pack(GROUP_ID, target_id, w, r, g, b, fade_ms)
    return _frame(MSG_CMD_PWM, payload)


# ─── Outgoing: discover ───────────────────────────────────────────────────────

def pack_discover() -> bytes:
    return _frame(MSG_DISCOVER, bytes([GROUP_ID]))


# WifiCtrlCommand: groupId(B) targetId(H) state(B) = 4 bytes
_WC = struct.Struct('<BHB')


def pack_wifi_ctrl(target_id: int = 0xFFFF, state: int = 1) -> bytes:
    payload = _WC.pack(GROUP_ID, target_id, state)
    return _frame(MSG_WIFI_CTRL, payload)


# RoleCtrlCommand: groupId(B) msgType(B) targetId(H) txEnabled(B) = 5 bytes
_RC2 = struct.Struct('<BBHB')


def pack_hub_pause(duration_sec: int = 10) -> bytes:
    return _frame(MSG_HUB_PAUSE, bytes([min(duration_sec, 255)]))


# AutonomousAnnounce: groupId(B) msgType(B) deviceId(H) state(B) reserved(B) = 6 bytes
_AUTO = struct.Struct('<BBHBx')


def parse_autonomous(payload: bytes) -> dict | None:
    if len(payload) < 4:
        return None
    g, mt, did, state = struct.unpack_from('<BBHB', payload)
    return {'deviceId': f'{did:04X}', 'state': 'autonomous' if state == 0 else 'restored'}


def pack_role_ctrl(target_id: int, tx_enabled: bool) -> bytes:
    payload = _RC2.pack(GROUP_ID, MSG_ROLE_CTRL, target_id, 1 if tx_enabled else 0)
    return _frame(MSG_ROLE_CTRL, payload)


# ─── Incoming (Hub → Mac) ─────────────────────────────────────────────────────

# IdentityResponse: groupId(B) marker(B) deviceId(H) role(B) firmware(8s) ip(4s)
_ID = struct.Struct('<BBH B8s4s')


def parse_identity(payload: bytes) -> dict | None:
    if len(payload) != _ID.size:
        return None
    g, marker, did, role, fw, ip = _ID.unpack(payload)
    return {
        'deviceId':  f'{did:04X}',
        'role':      ROLES.get(role, 'unknown'),
        'firmware':  fw.rstrip(b'\x00').decode('ascii', errors='replace'),
        'ip':        '.'.join(str(b) for b in ip),
    }


def parse_staff_telemetry(payload: bytes) -> dict | None:
    if len(payload) != _ST.size:
        return None
    g, did, spd, ang, ax, ay, az, gx, gy, gz, mt = _ST.unpack(payload)
    return {
        'groupId': g, 'deviceId': did,
        'speed': round(spd, 4), 'angle': round(ang, 2),
        'accX': ax, 'accY': ay, 'accZ': az,
        'gyroX': gx, 'gyroY': gy, 'gyroZ': gz,
        'motionType': mt,
    }

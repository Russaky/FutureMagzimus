"""Serial framing protocol — mirrors firmware Protocol.h and SerialBridge.cpp."""
from __future__ import annotations
import struct

HEADER = b'\xAA\x55'

MSG_STAFF_TELEMETRY = 0x01
MSG_MIC_TELEMETRY   = 0x02
MSG_PEDAL_EVENT     = 0x03
MSG_CMD_STAFF       = 0x10
MSG_CMD_RELAY       = 0x11
MSG_CMD_PWM         = 0x12
MSG_CMD_PROGRESS    = 0x13
MSG_NET_STATUS      = 0x14
MSG_CMD_DMX         = 0x15
MSG_CMD_EFFECT_STAFF = 0x16  # serial framing layer (Mac↔Hub)
MSG_DISCOVER        = 0x20

# ESP-NOW payload-layer marker (Hub→Staff, inside the EffectCommand struct
# itself) — distinct from MSG_CMD_EFFECT_STAFF above, which is the outer
# serial frame type. Must match firmware/staff/include/Protocol.h MSG_CMD_EFFECT.
ESPNOW_MSG_CMD_EFFECT = 0x52
MSG_IDENTITY        = 0x21
MSG_EFFECT_LIST     = 0x22
MSG_WIFI_CTRL       = 0x30
MSG_ROLE_CTRL       = 0x31
MSG_CALIBRATE       = 0x32
MSG_PAIR_REQ        = 0x40
MSG_PAIR_ACK        = 0x41
MSG_HUB_ALIVE       = 0x60
MSG_HUB_PAUSE       = 0x61
MSG_AUTONOMOUS      = 0x62

# Staff command types
CMD_LED_OFF     = 0
CMD_LED_SOLID   = 1
CMD_LED_SPARKLE = 2
CMD_LED_FLAME   = 3
CMD_LED_RAINBOW = 4
CMD_LED_TILT    = 5
CMD_CALIBRATE   = 6

# Generic FastLED-based effect templates (EffectCommand, MSG_CMD_EFFECT_STAFF) —
# separate family from CMD_LED_* above, mirrors firmware/staff/include/Protocol.h.
# Naming/order follows docs/EffectComposer_Proposal_v0.1.md §5 (Solid/Gradient/
# Wave/Fade/Sparkle). FX_THEATER_CHASE has no proposal equivalent, kept as bonus.
# FX_FLAME/FX_VERTICAL fold in the last two Legacy fixed-effects that didn't
# already have a generic equivalent — Legacy Effect is retired as a UI concept.
FX_SOLID         = 0
FX_GRADIENT      = 1
FX_WAVE          = 2
FX_FADE          = 3
FX_SPARKLE       = 4
FX_THEATER_CHASE = 5
FX_FLAME         = 6
FX_VERTICAL      = 7

# Effect color source (EffectCommand.colorMode)
COLOR_PALETTE = 0   # use paletteId (built-in FastLED gradient)
COLOR_CUSTOM  = 1   # use primary/secondary RGB below instead

# Built-in FastLED gradient palettes available to generic effects
PAL_RAINBOW = 0
PAL_HEAT    = 1
PAL_LAVA    = 2
PAL_OCEAN   = 3
PAL_FOREST  = 4
PAL_PARTY   = 5

# IMU-reactive parameter binding — resolved entirely on the Staff Master
# (it already reads its own IMU every tick); the Mac only tells it WHICH
# signal drives WHICH parameter. Mirrors firmware/staff/include/Protocol.h.
REACTIVE_NONE        = 0
REACTIVE_SPEED       = 1
REACTIVE_ANGLE       = 2
REACTIVE_ORIENTATION = 3
REACTIVE_SPIN        = 4

REACTIVE_PARAM_NONE      = 0
REACTIVE_PARAM_SPEED     = 1
REACTIVE_PARAM_INTENSITY = 2
REACTIVE_PARAM_PARAM1    = 3

# Staff telemetry flag masks
STAFF_FLAG_THROW        = 0x01
STAFF_FLAG_CATCH        = 0x02
STAFF_FLAG_SPIN_CW      = 0x04
STAFF_FLAG_ORIENT_MASK  = 0x18
STAFF_FLAG_ORIENT_VERT  = 0x00
STAFF_FLAG_ORIENT_HORIZ = 0x08
STAFF_FLAG_ORIENT_INV   = 0x10
STAFF_FLAG_IMPACT       = 0x20

# Pedal event types
PEDAL_SHORT   = 0
PEDAL_LONG    = 1
PEDAL_DOUBLE  = 2
PEDAL_TRIPLE  = 3
PEDAL_PRESS   = 4
PEDAL_RELEASE = 5

# Network status codes
NET_STATUS_NO_BRAIN = 0
NET_STATUS_MISSING  = 1
NET_STATUS_OK       = 2

MSG_PAIR_REQ    = 0x40
MSG_PAIR_ACK    = 0x41
MSG_CALIBRATE   = 0x32
MSG_HUB_PAUSE   = 0x61
MSG_AUTONOMOUS  = 0x62

ROLES = {1: 'staff', 2: 'relay', 3: 'pwm', 4: 'progressbar', 5: 'mic', 6: 'pedal', 7: 'dmx'}

GROUP_ID = 1

# msg_type byte → human-readable label, used by the network traffic console
MSG_NAMES = {
    MSG_STAFF_TELEMETRY: 'STAFF_TELEMETRY',
    MSG_MIC_TELEMETRY:   'MIC_TELEMETRY',
    MSG_PEDAL_EVENT:     'PEDAL_EVENT',
    MSG_CMD_STAFF:       'CMD_STAFF',
    MSG_CMD_RELAY:       'CMD_RELAY',
    MSG_CMD_PWM:         'CMD_PWM',
    MSG_CMD_PROGRESS:    'CMD_PROGRESS',
    MSG_NET_STATUS:      'NET_STATUS',
    MSG_CMD_DMX:         'CMD_DMX',
    MSG_CMD_EFFECT_STAFF: 'CMD_EFFECT_STAFF',
    MSG_DISCOVER:        'DISCOVER',
    MSG_IDENTITY:        'IDENTITY',
    MSG_EFFECT_LIST:     'EFFECT_LIST',
    MSG_WIFI_CTRL:       'WIFI_CTRL',
    MSG_ROLE_CTRL:       'ROLE_CTRL',
    MSG_CALIBRATE:       'CALIBRATE',
    MSG_PAIR_REQ:        'PAIR_REQ',
    MSG_PAIR_ACK:        'PAIR_ACK',
    MSG_HUB_ALIVE:       'HUB_ALIVE',
    MSG_HUB_PAUSE:       'HUB_PAUSE',
    MSG_AUTONOMOUS:      'AUTONOMOUS',
}

# Struct formats (little-endian, packed — no padding)
# StaffTelemetry: groupId(B) deviceId(H) speed(f) angle(f) acc(3×h) gyro(3×h) motionType(B) flags(B) = 25 bytes
_ST  = struct.Struct('<BHffhhhhhhBB')
# HubCommand:     groupId(B) targetId(H) cmdType(B) r(B) g(B) b(B) brightness(B) = 8 bytes
_HC  = struct.Struct('<BHBBBBB')
# RelayCommand:   groupId(B) targetId(B) state(B) durationMs(H) = 5 bytes
_RC  = struct.Struct('<BBBH')
# PWMCommand:     groupId(B) targetId(B) w(B) r(B) g(B) b(B) fadeMs(H) = 8 bytes
_PWM = struct.Struct('<BBBBBBH')
# MicTelemetry:   groupId(B) deviceId(H) rms(f) peak(f) frequency(f) = 15 bytes
_MT  = struct.Struct('<BHfff')
# PedalEvent:     groupId(B) deviceId(H) eventType(B) = 4 bytes
_PE  = struct.Struct('<BHB')
# ProgressCommand: groupId(B) targetId(B) mode(B) value(B) r(B) g(B) b(B) fadeMs(H) = 9 bytes
_PC  = struct.Struct('<BBBBBBBB H')
# NetStatusCommand: groupId(B) targetId(B) status(B) = 3 bytes
_NS  = struct.Struct('<BBB')
# DMXCommand: groupId(B) targetAddr(H) w(B) r(B) g(B) b(B) = 7 bytes
_DMX = struct.Struct('<BHBBBB')
# EffectCommand: groupId(B) msgType(B) targetId(H) templateId(B) paletteId(B)
#                speed(B) intensity(B) param1(B) param2(B)
#                reactiveSource(B) reactiveParam(B) colorMode(B)
#                pr(B) pg(B) pb(B) sr(B) sg(B) sb(B) = 19 bytes
_FX  = struct.Struct('<BBHBBBBBBBBBBBBBBB')
# WifiCtrlCommand: groupId(B) targetId(H) state(B) = 4 bytes
_WC = struct.Struct('<BHB')
# RoleCtrlCommand: groupId(B) msgType(B) targetId(H) txEnabled(B) = 5 bytes
_RC2 = struct.Struct('<BBHB')


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


def pack_progress_command(target_id: int, mode: int, value: int,
                          r: int, g: int, b: int, fade_ms: int = 0) -> bytes:
    """Send a progress bar command.
    mode=0: progress bar (value 0-100 fills LEDs left-to-right)
    mode=1: solid color (r/g/b applied to all 100 LEDs)
    """
    payload = struct.pack('<BBBBBBBH', GROUP_ID, target_id, mode, value, r, g, b, fade_ms)
    return _frame(MSG_CMD_PROGRESS, payload)


def pack_net_status(target_id: int = 0xFF, status: int = NET_STATUS_OK) -> bytes:
    payload = _NS.pack(GROUP_ID, target_id, status)
    return _frame(MSG_NET_STATUS, payload)


def pack_dmx_command(target_addr: int, w: int, r: int, g: int, b: int) -> bytes:
    """Set 4 DMX channels (w/r/g/b) starting at target_addr (1-512)."""
    payload = _DMX.pack(GROUP_ID, target_addr, w, r, g, b)
    return _frame(MSG_CMD_DMX, payload)


def pack_effect_command(target_id: int, template_id: int, palette_id: int,
                        speed: int, intensity: int, param1: int = 0, param2: int = 0,
                        reactive_source: int = REACTIVE_NONE,
                        reactive_param: int = REACTIVE_PARAM_NONE,
                        color_mode: int = COLOR_PALETTE,
                        pr: int = 0, pg: int = 0, pb: int = 0,
                        sr: int = 0, sg: int = 0, sb: int = 0) -> bytes:
    """Generic parametrized FastLED effect — separate command family from
    pack_staff_command's 6 fixed CmdType effects. See FX_*/PAL_* constants above.
    reactive_source/reactive_param optionally bind one parameter to the
    staff's own live IMU signal instead of the static byte passed here —
    see REACTIVE_*/REACTIVE_PARAM_* above. color_mode selects between the
    built-in palette_id (COLOR_PALETTE, default) or a custom primary/secondary
    RGB gradient (COLOR_CUSTOM) — see COLOR_* above."""
    payload = _FX.pack(GROUP_ID, ESPNOW_MSG_CMD_EFFECT, target_id, template_id,
                       palette_id, speed, intensity, param1, param2,
                       reactive_source, reactive_param, color_mode,
                       pr, pg, pb, sr, sg, sb)
    return _frame(MSG_CMD_EFFECT_STAFF, payload)


def pack_discover() -> bytes:
    return _frame(MSG_DISCOVER, bytes([GROUP_ID]))


def pack_wifi_ctrl(target_id: int = 0xFFFF, state: int = 1) -> bytes:
    payload = _WC.pack(GROUP_ID, target_id, state)
    return _frame(MSG_WIFI_CTRL, payload)


def pack_hub_pause(duration_sec: int = 10) -> bytes:
    return _frame(MSG_HUB_PAUSE, bytes([min(duration_sec, 255)]))


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
    g, did, spd, ang, ax, ay, az, gx, gy, gz, mt, flags = _ST.unpack(payload)
    orient_raw = flags & STAFF_FLAG_ORIENT_MASK
    orient = {STAFF_FLAG_ORIENT_VERT: 'vertical',
               STAFF_FLAG_ORIENT_HORIZ: 'horizontal',
               STAFF_FLAG_ORIENT_INV: 'inverted'}.get(orient_raw, 'unknown')
    return {
        'groupId': g, 'deviceId': did,
        'speed': round(spd, 4), 'angle': round(ang, 2),
        'accX': ax, 'accY': ay, 'accZ': az,
        'gyroX': gx, 'gyroY': gy, 'gyroZ': gz,
        'motionType': mt,
        'flags': flags,
        'throw':         bool(flags & STAFF_FLAG_THROW),
        'catch':         bool(flags & STAFF_FLAG_CATCH),
        'spin_cw':       bool(flags & STAFF_FLAG_SPIN_CW),
        'orientation':   orient,
        'impact':        bool(flags & STAFF_FLAG_IMPACT),
    }


def parse_mic_telemetry(payload: bytes) -> dict | None:
    if len(payload) != _MT.size:
        return None
    g, did, rms, peak, freq = _MT.unpack(payload)
    return {
        'groupId':   g,
        'deviceId':  did,
        'rms':       round(rms, 4),
        'peak':      round(peak, 4),
        'frequency': round(freq, 2),
    }


def parse_pedal_event(payload: bytes) -> dict | None:
    if len(payload) != _PE.size:
        return None
    g, did, evtype = _PE.unpack(payload)
    ev_names = {0: 'short', 1: 'long', 2: 'double', 3: 'triple',
                4: 'press', 5: 'release'}
    return {
        'groupId':   g,
        'deviceId':  did,
        'eventType': ev_names.get(evtype, str(evtype)),
    }


def parse_effect_list(payload: bytes) -> dict | None:
    """Parse MSG_EFFECT_LIST: header(5 bytes) + N × (effectId(1) + name(8))."""
    if len(payload) < 5:
        return None
    g, msg_type, did, count = struct.unpack_from('<BBHB', payload)
    effects = []
    offset = 5
    for _ in range(count):
        if offset + 9 > len(payload):
            break
        eid = payload[offset]
        name = payload[offset+1:offset+9].rstrip(b'\x00').decode('ascii', errors='replace')
        effects.append({'effectId': eid, 'name': name})
        offset += 9
    return {'groupId': g, 'deviceId': did, 'effects': effects}


def parse_autonomous(payload: bytes) -> dict | None:
    if len(payload) < 4:
        return None
    g, mt, did, state = struct.unpack_from('<BBHB', payload)
    return {'deviceId': f'{did:04X}', 'state': 'autonomous' if state == 0 else 'restored'}

#pragma once
#include <stdint.h>

// ─── Motion types (resolved Hub-side, staff sends raw data) ───────────────────
enum MotionType : uint8_t {
    MOTION_IDLE  = 0,
    MOTION_SWING = 1,
    MOTION_SPIN  = 2,
};

// ─── Command types (Hub → Staff) ─────────────────────────────────────────────
enum CmdType : uint8_t {
    CMD_LED_OFF     = 0,
    CMD_LED_SOLID   = 1,
    CMD_LED_SPARKLE = 2,  // r/g/b = color, brightness = density (0–255)
    CMD_LED_FLAME   = 3,  // flickering warm flame, no params needed
    CMD_LED_RAINBOW = 4,  // rotating rainbow across the strip
    CMD_LED_TILT    = 5,  // IMU tilt color — r=hue (sync packets only)
    CMD_CALIBRATE   = 6,  // trigger gyro calibration (staff must be static)
    CMD_LED_VERTICAL = 7, // local preset: green near vertical-up (|angle|<=window),
                          // blue otherwise — driven by own IMU (sync packets: r=0/1 flag)
};

// ─── Staff telemetry flags (bit mask in StaffTelemetry.flags) ────────────────
#define STAFF_FLAG_THROW        0x01  // projectile launch detected
#define STAFF_FLAG_CATCH        0x02  // catch after free-fall
#define STAFF_FLAG_SPIN_CW      0x04  // 1=CW, 0=CCW (valid when spinning)
#define STAFF_FLAG_ORIENT_MASK  0x18  // 2-bit orientation field at bits 3-4
#define STAFF_FLAG_ORIENT_VERT  0x00  // vertical  (|pitch| < 30°)
#define STAFF_FLAG_ORIENT_HORIZ 0x08  // horizontal
#define STAFF_FLAG_ORIENT_INV   0x10  // inverted  (|pitch| > 150°)
#define STAFF_FLAG_IMPACT       0x20  // sudden high-g impact

// ─── Staff → Hub (25 bytes) ───────────────────────────────────────────────────
struct __attribute__((packed)) StaffTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;   // last 2 bytes of MAC
    float    speed;      // rotation magnitude (rad/s)
    float    angle;      // pitch (degrees)
    int16_t  accX, accY, accZ;
    int16_t  gyroX, gyroY, gyroZ;
    uint8_t  motionType;
    uint8_t  flags;      // STAFF_FLAG_* bitmask
};

// ─── Hub → Staff (8 bytes) ────────────────────────────────────────────────────
struct __attribute__((packed)) HubCommand {
    uint8_t  groupId;
    uint16_t targetId;   // 0xFFFF = broadcast to all staffs
    uint8_t  cmdType;
    uint8_t  r, g, b;
    uint8_t  brightness;
};

// ─── Discovery + WiFi control (shared) ───────────────────────────────────────
#define MSG_DISCOVER     0x20
#define MSG_IDENTITY     0x21
#define MSG_EFFECT_LIST  0x22
#define MSG_WIFI_CTRL  0x30
#define MSG_ROLE_CTRL  0x31
#define MSG_CALIBRATE  0x32
#define MSG_PAIR_REQ   0x40
#define MSG_PAIR_ACK   0x41
#define MSG_SYNC       0x50
#define MSG_SYNC_EFFECT 0x51  // Master → Slave: mirror active generic-effect params
#define MSG_CMD_EFFECT  0x52  // Hub → Staff: generic parametrized FastLED effect
#define MSG_HUB_ALIVE  0x60
#define MSG_AUTONOMOUS 0x62   // Staff → Hub → Mac: autonomous mode change

// ─── Generic effect templates (FastLED-based, parametrized) ──────────────────
// Added alongside the fixed CmdType effects above — does not replace them.
// A new effect = a new (templateId, paletteId, speed, intensity, param1, param2)
// preset, no firmware flash required.
//
// Naming/order follows docs/EffectComposer_Proposal_v0.1.md §5 (Solid/Gradient/
// Wave/Fade/Sparkle taxonomy). FX_NOISE_FIELD was dropped rather than kept as a
// 6th slot: Perlin noise reads as flat static on a 25-LED strip this short, it
// needs more pixels to look like a coherent field. FX_THEATER_CHASE has no
// equivalent in the proposal's 5 and is kept as-is (bonus slot).
// FX_FLAME/FX_VERTICAL fold in the last two Legacy fixed-CmdType effects that
// didn't already have a generic equivalent (Solid/Sparkle/Rainbow do, via
// Solid/Sparkle/Gradient+Rainbow-palette) — Legacy Effect is retired as a
// separate UI family, everything lives here now.
enum EffectTemplate : uint8_t {
    FX_SOLID         = 0,  // uniform color across the strip (intensity = brightness)
    FX_GRADIENT      = 1,  // scrolling palette gradient (was Palette Cycle); param1 = direction (<128 fwd, >=128 rev)
    FX_WAVE          = 2,  // moving point with fading trail (was Sinelon); param1 = trail width
    FX_FADE          = 3,  // global breathing brightness pulse (was BPM); param1 = min brightness, param2 = max brightness
    FX_SPARKLE       = 4,  // random fading sparkles (was Confetti); speed = density, param1 = decay
    FX_THEATER_CHASE = 5,  // classic 1-of-3 marquee chase (unchanged, bonus — no proposal equivalent)
    FX_FLAME         = 6,  // Fire2012-style flame simulation (was Legacy Flame); speed = cooling, param1 = sparking
    FX_VERTICAL      = 7,  // green near-vertical / blue otherwise (was Legacy Vertical); param1 = angle window (deg)
};
#define NUM_EFFECT_TEMPLATES 8

// ─── Generic effect palettes (FastLED built-in gradient palettes) ───────────
enum EffectPalette : uint8_t {
    PAL_RAINBOW = 0,
    PAL_HEAT    = 1,
    PAL_LAVA    = 2,
    PAL_OCEAN   = 3,
    PAL_FOREST  = 4,
    PAL_PARTY   = 5,
};
#define NUM_EFFECT_PALETTES 6

// ─── Effect color source ──────────────────────────────────────────────────
// COLOR_PALETTE (default): paletteId selects one of the NUM_EFFECT_PALETTES
// built-in FastLED gradients, exactly as before.
// COLOR_CUSTOM: primary/secondary RGB build a 2-stop gradient on the fly
// (resolvePalette() in LedManager) — every existing template already renders
// through ColorFromPalette(), so this needs no per-template special-casing.
enum EffectColorMode : uint8_t {
    COLOR_PALETTE = 0,
    COLOR_CUSTOM  = 1,
};

// ─── IMU-reactive parameter binding ───────────────────────────────────────
// Optionally lets ONE generic-effect parameter track the staff's own live
// IMU signal instead of a fixed byte. Resolved entirely on the Master each
// telemetry tick (it already reads its own IMU locally, see main.cpp) —
// no extra radio traffic, no protocol change on the Master→Slave link:
// EffectSyncPacket keeps carrying already-resolved values either way.
enum ReactiveSource : uint8_t {
    REACTIVE_NONE        = 0,
    REACTIVE_SPEED       = 1,  // rotation speed magnitude
    REACTIVE_ANGLE       = 2,  // tilt angle
    REACTIVE_ORIENTATION = 3,  // vertical/horizontal/inverted band
    REACTIVE_SPIN        = 4,  // CW / CCW
};
enum ReactiveParam : uint8_t {
    REACTIVE_PARAM_NONE      = 0,
    REACTIVE_PARAM_SPEED     = 1,
    REACTIVE_PARAM_INTENSITY = 2,
    REACTIVE_PARAM_PARAM1    = 3,
};

// Hub → Staff (19 bytes) — generic parametrized effect command.
// Kept as a SEPARATE struct/msgType from HubCommand (not a mutation of it) —
// HubCommand's 6 fixed effects and its 8-byte size are untouched, see the
// 2026-06-08 postmortem on HubCommand/SyncPacket 8-byte collision in DONE.md.
// msgType is checked explicitly (not size-only) before any generic-size fallback.
struct __attribute__((packed)) EffectCommand {
    uint8_t  groupId;
    uint8_t  msgType;     // = MSG_CMD_EFFECT
    uint16_t targetId;    // 0xFFFF = broadcast to all staffs
    uint8_t  templateId;  // EffectTemplate
    uint8_t  paletteId;   // EffectPalette — used when colorMode == COLOR_PALETTE
    uint8_t  speed;       // 0-255 (static value — ignored if reactiveParam overrides this field)
    uint8_t  intensity;   // 0-255 (static value — ditto)
    uint8_t  param1;      // template-specific (static value — ditto)
    uint8_t  param2;      // template-specific
    uint8_t  reactiveSource; // ReactiveSource — 0 = fully static, use fields above as-is
    uint8_t  reactiveParam;  // ReactiveParam — which field above gets overridden
    uint8_t  colorMode;   // EffectColorMode
    uint8_t  pr, pg, pb;  // primary color — used when colorMode == COLOR_CUSTOM
    uint8_t  sr, sg, sb;  // secondary color — ditto
};

// Master → Slave (17 bytes) — mirrors the active generic effect, same shape
// as EffectCommand but with masterId instead of targetId (matches SyncPacket's
// own master/target field swap). Sent INSTEAD OF SyncPacket for a given tick,
// never both — see 2026-07-19 DONE.md root-cause-2 (extra esp_now_send() per
// tick congested the radio and dropped sync packets to the slave).
struct __attribute__((packed)) EffectSyncPacket {
    uint8_t  groupId;
    uint8_t  msgType;     // = MSG_SYNC_EFFECT
    uint16_t masterId;
    uint8_t  templateId;
    uint8_t  paletteId;
    uint8_t  speed;
    uint8_t  intensity;
    uint8_t  param1;
    uint8_t  param2;
    uint8_t  colorMode;
    uint8_t  pr, pg, pb;
    uint8_t  sr, sg, sb;
};

struct __attribute__((packed)) AutonomousAnnounce {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_AUTONOMOUS
    uint16_t deviceId;
    uint8_t  state;      // 0=hub_lost, 1=hub_restored
    uint8_t  reserved;
};

struct __attribute__((packed)) WifiCtrlCommand {
    uint8_t  groupId;
    uint16_t targetId;
    uint8_t  state;
};

struct __attribute__((packed)) RoleCtrlCommand {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_ROLE_CTRL (disambiguates from WifiCtrlCommand by size)
    uint16_t targetId;
    uint8_t  txEnabled;  // 1 = send telemetry, 0 = silent
};

// Staff → Hub (11 bytes)
struct __attribute__((packed)) PairingRequest {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_PAIR_REQ
    uint16_t deviceId;
    uint8_t  staffId;    // NVS logical ID (0 = unassigned)
    uint8_t  mac[6];
};

// Hub → Staff (10 bytes)
struct __attribute__((packed)) PairingAck {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_PAIR_ACK
    uint16_t targetId;
    uint8_t  hubMac[6];
};

// Master → Slave (9 bytes): current LED state for mirroring
struct __attribute__((packed)) SyncPacket {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_SYNC
    uint16_t masterId;
    uint8_t  cmdType;    // CMD_LED_* (CMD_LED_TILT uses r=hue)
    uint8_t  r, g, b;
};

struct __attribute__((packed)) DiscoverRequest {
    uint8_t groupId;
    uint8_t marker;   // = MSG_DISCOVER
};

struct __attribute__((packed)) IdentityResponse {
    uint8_t  groupId;
    uint8_t  marker;  // = MSG_IDENTITY
    uint16_t deviceId;
    uint8_t  role;
    char     firmware[8];
    uint8_t  ip[4];
};

// Staff → PWM (8 bytes)
struct __attribute__((packed)) PWMCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all PWM nodes
    uint8_t  w, r, g, b;
    uint16_t fadeMs;
};

// Staff → DMX Controller (7 bytes) — mirrors the Staff's own active LED color
struct __attribute__((packed)) DMXCommand {
    uint8_t  groupId;
    uint16_t targetAddr; // DMX channel start address (1-512)
    uint8_t  w, r, g, b; // written at targetAddr, +1, +2, +3
};

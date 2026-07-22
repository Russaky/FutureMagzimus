#pragma once
#include <stdint.h>

// ─── Serial frame types (Hub ↔ Mac) ──────────────────────────────────────────
enum SerialMsgType : uint8_t {
    MSG_STAFF_TELEMETRY = 0x01,  // Hub → Mac
    MSG_MIC_TELEMETRY   = 0x02,  // Mic → Hub → Mac
    MSG_PEDAL_EVENT     = 0x03,  // Pedal → Hub → Mac
    MSG_CMD_STAFF       = 0x10,  // Mac → Hub → Staff
    MSG_CMD_RELAY       = 0x11,  // Mac → Hub → Relay
    MSG_CMD_PWM         = 0x12,  // Mac → Hub → PWM
    MSG_CMD_PROGRESS    = 0x13,  // Mac → Hub → ProgressBar
    MSG_NET_STATUS      = 0x14,  // Hub → Pedal: LED network status
    MSG_CMD_DMX         = 0x15,  // Mac → Hub → DMX Controller
    MSG_CMD_EFFECT_STAFF = 0x16, // Mac → Hub → Staff: generic parametrized FastLED effect
    MSG_DISCOVER        = 0x20,  // Mac → Hub → broadcast ESP-NOW
    MSG_IDENTITY        = 0x21,  // Device → Hub → Mac
    MSG_EFFECT_LIST     = 0x22,  // Device → Hub → Mac: supported effects
    MSG_WIFI_CTRL       = 0x30,  // Mac → Hub → Device: enable/disable WiFi
    MSG_ROLE_CTRL       = 0x31,  // Mac → Hub → Staff: set tx_enabled (NVS)
    MSG_CALIBRATE       = 0x32,  // Mac → Hub → Staff: trigger gyro calibration
    MSG_PAIR_REQ        = 0x40,  // Staff → Hub → Mac: pairing request
    MSG_PAIR_ACK        = 0x41,  // Mac → Hub → Staff: pairing ack
    MSG_HUB_ALIVE       = 0x60,  // Hub → Staff: periodic keepalive (1/sec)
    MSG_HUB_PAUSE       = 0x61,  // Mac → Hub: pause keepalive for N seconds (Serial only)
    MSG_AUTONOMOUS      = 0x62,  // Staff → Hub → Mac: staff entered/exited autonomous mode
};

// ─── Device roles ─────────────────────────────────────────────────────────────
enum DeviceRole : uint8_t {
    ROLE_STAFF = 1,
    ROLE_RELAY = 2,
    ROLE_PWM   = 3,
    ROLE_DMX   = 7,
};

// ─── ESP-NOW packets ──────────────────────────────────────────────────────────

// ─── Staff telemetry flags ────────────────────────────────────────────────────
#define STAFF_FLAG_THROW        0x01
#define STAFF_FLAG_CATCH        0x02
#define STAFF_FLAG_SPIN_CW      0x04
#define STAFF_FLAG_ORIENT_MASK  0x18
#define STAFF_FLAG_ORIENT_VERT  0x00
#define STAFF_FLAG_ORIENT_HORIZ 0x08
#define STAFF_FLAG_ORIENT_INV   0x10
#define STAFF_FLAG_IMPACT       0x20

// Staff → Hub (25 bytes)
struct __attribute__((packed)) StaffTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;
    float    speed;
    float    angle;
    int16_t  accX, accY, accZ;
    int16_t  gyroX, gyroY, gyroZ;
    uint8_t  motionType;
    uint8_t  flags;    // STAFF_FLAG_* bitmask
};

// Hub → Staff (8 bytes)
struct __attribute__((packed)) HubCommand {
    uint8_t  groupId;
    uint16_t targetId;   // 0xFFFF = broadcast to all staffs
    uint8_t  cmdType;    // 0=OFF, 1=SOLID
    uint8_t  r, g, b;
    uint8_t  brightness;
};

// Hub → Relay (5 bytes)
struct __attribute__((packed)) RelayCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all relays
    uint8_t  state;      // 0=OFF, 1=ON
    uint16_t durationMs; // auto-shutoff (0 = manual)
};

// Hub → PWM (8 bytes)
struct __attribute__((packed)) PWMCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all PWM nodes
    uint8_t  w, r, g, b;
    uint16_t fadeMs;     // fade duration (0 = instant)
};

// Hub → DMX Controller (7 bytes)
struct __attribute__((packed)) DMXCommand {
    uint8_t  groupId;
    uint16_t targetAddr; // DMX channel start address (1-512)
    uint8_t  w, r, g, b; // written at targetAddr, +1, +2, +3
};

// Hub → Staff (19 bytes) — generic parametrized FastLED effect. Kept as a
// separate struct/msgType from HubCommand (not a mutation of it) — see the
// 2026-06-08 postmortem on HubCommand/SyncPacket 8-byte collision in DONE.md.
// Mirrors firmware/staff/include/Protocol.h's EffectCommand exactly; the Hub
// only forwards the raw bytes, it never interprets them. IMPORTANT: this
// struct must be kept byte-for-byte in sync with the Staff's copy — the Hub
// validates incoming length against sizeof(EffectCommand) before forwarding
// (see main.cpp MSG_CMD_EFFECT_STAFF), so a stale copy here silently drops
// every effect command instead of forwarding it.
struct __attribute__((packed)) EffectCommand {
    uint8_t  groupId;
    uint8_t  msgType;     // = 0x52 (MSG_CMD_EFFECT at the ESP-NOW layer)
    uint16_t targetId;    // 0xFFFF = broadcast to all staffs
    uint8_t  templateId;
    uint8_t  paletteId;
    uint8_t  speed;
    uint8_t  intensity;
    uint8_t  param1;
    uint8_t  param2;
    uint8_t  reactiveSource;  // ReactiveSource (see firmware/staff/include/Protocol.h)
    uint8_t  reactiveParam;   // ReactiveParam
    uint8_t  colorMode;       // EffectColorMode
    uint8_t  pr, pg, pb;      // primary color (custom mode)
    uint8_t  sr, sg, sb;      // secondary color (custom mode)
};

// Staff → Hub (6 bytes) — staff entered/exited autonomous mode
struct __attribute__((packed)) AutonomousAnnounce {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_AUTONOMOUS
    uint16_t deviceId;
    uint8_t  state;      // 0=hub_lost → autonomous, 1=hub_restored
    uint8_t  reserved;
};

// Staff → Hub (11 bytes) — sent at boot
struct __attribute__((packed)) PairingRequest {
    uint8_t  groupId;
    uint8_t  msgType;
    uint16_t deviceId;
    uint8_t  staffId;
    uint8_t  mac[6];
};

// Hub → Staff (10 bytes)
struct __attribute__((packed)) PairingAck {
    uint8_t  groupId;
    uint8_t  msgType;
    uint16_t targetId;
    uint8_t  hubMac[6];
};

// Mac → Hub → Staff (4 bytes) — set telemetry tx role (persisted to NVS)
struct __attribute__((packed)) RoleCtrlCommand {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_ROLE_CTRL (disambiguates from WifiCtrlCommand by size)
    uint16_t targetId;   // specific deviceId or 0xFFFF
    uint8_t  txEnabled;  // 1 = send telemetry, 0 = silent (Rx-Only head)
};

// Mac → Hub → Device (4 bytes) — turn WiFi on/off
struct __attribute__((packed)) WifiCtrlCommand {
    uint8_t  groupId;
    uint16_t targetId;  // 0xFFFF = all devices
    uint8_t  state;     // 1=enable, 0=disable
};

// Hub → All (2 bytes) — ESP-NOW broadcast to trigger identity responses
struct __attribute__((packed)) DiscoverRequest {
    uint8_t groupId;
    uint8_t marker;      // = MSG_DISCOVER
};

// Device → Hub (17 bytes) — ESP-NOW response to discover
struct __attribute__((packed)) IdentityResponse {
    uint8_t  groupId;
    uint8_t  marker;     // = MSG_IDENTITY
    uint16_t deviceId;
    uint8_t  role;       // DeviceRole
    char     firmware[8];
    uint8_t  ip[4];      // WiFi IP if available, else 0.0.0.0
};

// Mic → Hub (15 bytes) — ambient audio metrics
struct __attribute__((packed)) MicTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;
    float    rms;        // root mean square amplitude
    float    peak;       // peak amplitude in window
    float    frequency;  // dominant frequency (Hz) from FFT
};

// Pedal → Hub (4 bytes) — button event
enum PedalEventType : uint8_t {
    PEDAL_SHORT  = 0,
    PEDAL_LONG   = 1,
    PEDAL_DOUBLE = 2,
    PEDAL_TRIPLE = 3,
    PEDAL_PRESS  = 4,   // raw press (for custom timing)
    PEDAL_RELEASE= 5,
};

struct __attribute__((packed)) PedalEvent {
    uint8_t  groupId;
    uint16_t deviceId;
    uint8_t  eventType;  // PedalEventType
};

// Hub → PWM/Progress bar (9 bytes) — WRGB or progress bar command
struct __attribute__((packed)) ProgressCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all progress bars
    uint8_t  mode;       // 0=progress bar, 1=solid color
    uint8_t  value;      // 0-100 for progress mode, ignored for solid
    uint8_t  r, g, b;
    uint16_t fadeMs;
};

// Hub → Pedal (3 bytes) — LED status indicator
enum NetStatus : uint8_t {
    NET_STATUS_NO_BRAIN = 0,   // red
    NET_STATUS_MISSING  = 1,   // yellow
    NET_STATUS_OK       = 2,   // green
};

struct __attribute__((packed)) NetStatusCommand {
    uint8_t groupId;
    uint8_t targetId;    // 0xFF = all pedals
    uint8_t status;      // NetStatus
};

// Device → Hub (variable) — effect list at boot
#define EFFECT_NAME_LEN 8
struct __attribute__((packed)) EffectListHeader {
    uint8_t  groupId;
    uint8_t  msgType;    // = MSG_EFFECT_LIST
    uint16_t deviceId;
    uint8_t  count;
    // followed by count × EffectEntry (effectId + name[8])
};
struct __attribute__((packed)) EffectEntry {
    uint8_t effectId;
    char    name[EFFECT_NAME_LEN];
};

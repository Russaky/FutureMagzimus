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
};

// ─── Staff → Hub (24 bytes) ───────────────────────────────────────────────────
struct __attribute__((packed)) StaffTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;   // last 2 bytes of MAC
    float    speed;      // rotation magnitude (rad/s)
    float    angle;      // pitch (degrees)
    int16_t  accX, accY, accZ;
    int16_t  gyroX, gyroY, gyroZ;
    uint8_t  motionType;
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
#define MSG_DISCOVER   0x20
#define MSG_IDENTITY   0x21
#define MSG_WIFI_CTRL  0x30
#define MSG_ROLE_CTRL  0x31
#define MSG_CALIBRATE  0x32
#define MSG_PAIR_REQ   0x40
#define MSG_PAIR_ACK   0x41
#define MSG_SYNC       0x50
#define MSG_HUB_ALIVE  0x60
#define MSG_AUTONOMOUS 0x62   // Staff → Hub → Mac: autonomous mode change

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

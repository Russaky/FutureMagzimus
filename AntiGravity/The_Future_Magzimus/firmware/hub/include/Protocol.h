#pragma once
#include <stdint.h>

// ─── Serial frame types (Hub ↔ Mac) ──────────────────────────────────────────
enum SerialMsgType : uint8_t {
    MSG_STAFF_TELEMETRY = 0x01,  // Hub → Mac
    MSG_CMD_STAFF       = 0x10,  // Mac → Hub → Staff
    MSG_CMD_RELAY       = 0x11,  // Mac → Hub → Relay
    MSG_CMD_PWM         = 0x12,  // Mac → Hub → PWM
    MSG_DISCOVER        = 0x20,  // Mac → Hub → broadcast ESP-NOW
    MSG_IDENTITY        = 0x21,  // Device → Hub → Mac
    MSG_WIFI_CTRL       = 0x30,  // Mac → Hub → Device: enable/disable WiFi
    MSG_ROLE_CTRL       = 0x31,  // Mac → Hub → Staff: set tx_enabled (NVS)
    MSG_PAIR_REQ        = 0x40,  // Staff → Hub → Mac: pairing request
    MSG_PAIR_ACK        = 0x41,  // Mac → Hub → Staff: pairing ack
    MSG_CALIBRATE       = 0x32,  // Mac → Hub → Staff: trigger gyro calibration
    MSG_HUB_ALIVE       = 0x60,  // Hub → Staff: periodic keepalive (1/sec)
    MSG_HUB_PAUSE       = 0x61,  // Mac → Hub: pause keepalive for N seconds (Serial only)
    MSG_AUTONOMOUS      = 0x62,  // Staff → Hub → Mac: staff entered/exited autonomous mode
};

// ─── Device roles ─────────────────────────────────────────────────────────────
enum DeviceRole : uint8_t {
    ROLE_STAFF = 1,
    ROLE_RELAY = 2,
    ROLE_PWM   = 3,
};

// ─── ESP-NOW packets ──────────────────────────────────────────────────────────

// Staff → Hub (24 bytes)
struct __attribute__((packed)) StaffTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;
    float    speed;
    float    angle;
    int16_t  accX, accY, accZ;
    int16_t  gyroX, gyroY, gyroZ;
    uint8_t  motionType;
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

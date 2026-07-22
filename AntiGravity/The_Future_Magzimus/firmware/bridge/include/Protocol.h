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
    MSG_DISCOVER        = 0x20,  // Mac → Hub → broadcast ESP-NOW
    MSG_IDENTITY        = 0x21,  // Device → Hub → Mac
    MSG_EFFECT_LIST     = 0x22,  // Device → Hub → Mac: supported effects
    MSG_WIFI_CTRL       = 0x30,  // Mac → Hub → Device: enable/disable WiFi
    MSG_ROLE_CTRL       = 0x31,  // Mac → Hub → Staff: set tx_enabled (NVS)
    MSG_CALIBRATE       = 0x32,  // Mac → Hub → Staff: trigger gyro calibration
    // custom pairing / status
    MSG_PAIR_REQ        = 0x40,
    MSG_PAIR_ACK        = 0x41,
    MSG_HUB_ALIVE       = 0x60,
    MSG_HUB_PAUSE       = 0x61,
    MSG_AUTONOMOUS      = 0x62,
};

// ─── Device roles ─────────────────────────────────────────────────────────────
enum DeviceRole : uint8_t {
    ROLE_STAFF = 1,
    ROLE_RELAY = 2,
    ROLE_PWM   = 3,
};

// ─── ESP-NOW packets ──────────────────────────────────────────────────────────

// Bridge → Node (5 bytes)
struct __attribute__((packed)) light_cmd_t {
    uint8_t targetId;   // 0 = broadcast to all nodes
    uint8_t w, r, g, b;
};

// Node → Bridge (5 bytes) — sent only when the node's state actually changes
struct __attribute__((packed)) light_ack_t {
    uint8_t nodeId;
    uint8_t w, r, g, b;
};

// DiscoverRequest (2 bytes)
struct __attribute__((packed)) DiscoverRequest {
    uint8_t groupId;
    uint8_t marker;      // = MSG_DISCOVER
};

// IdentityResponse (17 bytes)
struct __attribute__((packed)) IdentityResponse {
    uint8_t  groupId;
    uint8_t  marker;     // = MSG_IDENTITY
    uint16_t deviceId;
    uint8_t  role;       // DeviceRole
    char     firmware[8];
    uint8_t  ip[4];
};

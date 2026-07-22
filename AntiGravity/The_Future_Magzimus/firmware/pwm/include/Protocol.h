#pragma once
#include <stdint.h>

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

// ─── Discovery ────────────────────────────────────────────────────────────────
#define MSG_DISCOVER 0x20
#define MSG_IDENTITY 0x21

struct __attribute__((packed)) DiscoverRequest {
    uint8_t groupId;
    uint8_t marker;
};

struct __attribute__((packed)) IdentityResponse {
    uint8_t  groupId;
    uint8_t  marker;
    uint16_t deviceId;
    uint8_t  role;
    char     firmware[8];
    uint8_t  ip[4];
};

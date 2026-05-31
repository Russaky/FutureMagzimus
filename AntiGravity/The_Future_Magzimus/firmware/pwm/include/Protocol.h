#pragma once
#include <stdint.h>

// Hub → PWM (8 bytes)
struct __attribute__((packed)) PWMCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all PWM nodes, or last byte of MAC
    uint8_t  w, r, g, b;
    uint16_t fadeMs;     // fade duration (0 = instant)
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

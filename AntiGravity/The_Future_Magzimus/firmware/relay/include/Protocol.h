#pragma once
#include <stdint.h>

// Hub → Relay (5 bytes)
struct __attribute__((packed)) RelayCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all relays, or last byte of MAC
    uint8_t  state;      // 0=OFF, 1=ON
    uint16_t durationMs; // auto-shutoff (0 = manual)
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

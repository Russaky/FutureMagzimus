#pragma once
#include <stdint.h>

// Hub → DMX Controller (7 bytes)
struct __attribute__((packed)) DMXCommand {
    uint8_t  groupId;
    uint16_t targetAddr; // DMX channel start address (1-512)
    uint8_t  w, r, g, b; // written at targetAddr, +1, +2, +3
};

// ─── Discovery ────────────────────────────────────────────────────────────────
#define MSG_CMD_DMX  0x15
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

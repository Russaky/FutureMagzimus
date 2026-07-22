#pragma once
#include <stdint.h>

#define MSG_DISCOVER      0x20
#define MSG_IDENTITY      0x21
#define MSG_WIFI_CTRL     0x30
#define MSG_CMD_PROGRESS  0x13

// Hub → ProgressBar (9 bytes)
struct __attribute__((packed)) ProgressCommand {
    uint8_t  groupId;
    uint8_t  targetId;   // 0xFF = all progress bars
    uint8_t  mode;       // 0 = progress bar, 1 = solid color
    uint8_t  value;      // 0-100 for progress mode
    uint8_t  r, g, b;
    uint16_t fadeMs;
};

struct __attribute__((packed)) DiscoverRequest {
    uint8_t groupId;
    uint8_t marker;   // = MSG_DISCOVER
};

struct __attribute__((packed)) IdentityResponse {
    uint8_t  groupId;
    uint8_t  marker;  // = MSG_IDENTITY
    uint16_t deviceId;
    uint8_t  role;    // 4 = progress bar
    char     firmware[8];
    uint8_t  ip[4];
};

struct __attribute__((packed)) WifiCtrlCommand {
    uint8_t  groupId;
    uint16_t targetId;
    uint8_t  state;
};

#define ROLE_PROGRESS_BAR 4

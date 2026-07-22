#pragma once
#include <stdint.h>

#define MSG_MIC_TELEMETRY 0x02
#define MSG_DISCOVER      0x20
#define MSG_IDENTITY      0x21
#define MSG_WIFI_CTRL     0x30

// Mic → Hub (15 bytes)
struct __attribute__((packed)) MicTelemetry {
    uint8_t  groupId;
    uint16_t deviceId;
    float    rms;
    float    peak;
    float    frequency;
};

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

struct __attribute__((packed)) WifiCtrlCommand {
    uint8_t  groupId;
    uint16_t targetId;
    uint8_t  state;
};

#define ROLE_MIC 5

#pragma once
#include <stdint.h>

#define MSG_PEDAL_EVENT  0x03
#define MSG_NET_STATUS   0x14
#define MSG_DISCOVER     0x20
#define MSG_IDENTITY     0x21
#define MSG_WIFI_CTRL    0x30

// Pedal → Hub (4 bytes)
enum PedalEventType : uint8_t {
    PEDAL_SHORT   = 0,
    PEDAL_LONG    = 1,
    PEDAL_DOUBLE  = 2,
    PEDAL_TRIPLE  = 3,
    PEDAL_PRESS   = 4,
    PEDAL_RELEASE = 5,
};

struct __attribute__((packed)) PedalEvent {
    uint8_t  groupId;
    uint16_t deviceId;
    uint8_t  eventType;
};

// Hub → Pedal (3 bytes) — LED indicator control
enum NetStatus : uint8_t {
    NET_STATUS_NO_BRAIN = 0,  // red
    NET_STATUS_MISSING  = 1,  // yellow
    NET_STATUS_OK       = 2,  // green
};

struct __attribute__((packed)) NetStatusCommand {
    uint8_t groupId;
    uint8_t targetId;
    uint8_t status;
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

#define ROLE_PEDAL 6

#pragma once
#include "Protocol.h"
#include <stdint.h>

class EspNow {
public:
    static uint16_t deviceId;

    static void init();
    static void sendTelemetry(const StaffTelemetry &pkt);
    static void sendIdentity();
    static bool isHubAlive();
    static void setHubMac(const uint8_t *mac);  // switch telemetry to unicast after pairing
    static bool dequeueCommand(HubCommand &out);
    static bool dequeueWifiCtrl(WifiCtrlCommand &out);
    static bool dequeueRoleCtrl(RoleCtrlCommand &out);
    static bool dequeuePairingAck(PairingAck &out);
    static bool dequeueSyncPacket(SyncPacket &out);
    static bool dequeueEffectCommand(EffectCommand &out);
    static bool dequeueEffectSyncPacket(EffectSyncPacket &out);
    static void sendPairingRequest(uint8_t staffId);
    static void sendSyncPacket(uint8_t cmdType, uint8_t r, uint8_t g, uint8_t b);
    static void sendEffectSyncPacket(uint8_t templateId, uint8_t paletteId, uint8_t speed,
                                      uint8_t intensity, uint8_t param1, uint8_t param2,
                                      uint8_t colorMode, uint8_t pr, uint8_t pg, uint8_t pb,
                                      uint8_t sr, uint8_t sg, uint8_t sb);
    static void sendAutonomous(uint8_t state);  // 0=lost, 1=restored
    static void sendEffectList();               // MSG_EFFECT_LIST at boot
    static void sendPWMCommand(uint8_t targetId, uint8_t w, uint8_t r, uint8_t g, uint8_t b, uint16_t fadeMs);
    static void sendDMXCommand(uint16_t targetAddr, uint8_t w, uint8_t r, uint8_t g, uint8_t b);
};

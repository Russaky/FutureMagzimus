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
    static void sendPairingRequest(uint8_t staffId);
    static void sendSyncPacket(uint8_t cmdType, uint8_t r, uint8_t g, uint8_t b);
    static void sendAutonomous(uint8_t state);  // 0=lost, 1=restored
};

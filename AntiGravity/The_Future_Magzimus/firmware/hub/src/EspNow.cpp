#include "EspNow.h"
#include "Config.h"
#include "Protocol.h"
#include "SerialBridge.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

static uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

static uint8_t s_hubMac[6] = {};

static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(StaffTelemetry)) {
        const StaffTelemetry *pkt = (const StaffTelemetry *)data;
        if (pkt->groupId != GROUP_ID) return;
        SerialBridge::sendFrame(MSG_STAFF_TELEMETRY, data, (uint16_t)len);
    } else if (len == sizeof(IdentityResponse)) {
        const IdentityResponse *id = (const IdentityResponse *)data;
        if (id->groupId != GROUP_ID || id->marker != MSG_IDENTITY) return;
        SerialBridge::sendFrame(MSG_IDENTITY, data, (uint16_t)len);
    } else if (len == sizeof(AutonomousAnnounce)) {
        const AutonomousAnnounce *ann = (const AutonomousAnnounce *)data;
        if (ann->groupId != GROUP_ID || ann->msgType != MSG_AUTONOMOUS) return;
        SerialBridge::sendFrame(MSG_AUTONOMOUS, data, (uint16_t)len);
    } else if (len == sizeof(PairingRequest)) {
        const PairingRequest *req = (const PairingRequest *)data;
        if (req->groupId != GROUP_ID || req->msgType != MSG_PAIR_REQ) return;
        // Forward to Mac for logging
        SerialBridge::sendFrame(MSG_PAIR_REQ, data, (uint16_t)len);
        // Send PairingAck back to the requesting staff
        PairingAck ack = {};
        ack.groupId  = GROUP_ID;
        ack.msgType  = MSG_PAIR_ACK;
        ack.targetId = req->deviceId;
        memcpy(ack.hubMac, s_hubMac, 6);
        esp_now_send(broadcast, (const uint8_t *)&ack, sizeof(ack));
    }
}

void EspNow::init() {
    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);
    esp_wifi_get_mac(WIFI_IF_STA, s_hubMac);

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, broadcast, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);
}

void EspNow::send(const uint8_t *payload, uint16_t len) {
    esp_now_send(broadcast, payload, len);
}

void EspNow::sendDiscover() {
    DiscoverRequest req = { GROUP_ID, MSG_DISCOVER };
    esp_now_send(broadcast, (const uint8_t *)&req, sizeof(req));
}

void EspNow::sendAlive() {
    uint8_t pkt[2] = { GROUP_ID, MSG_HUB_ALIVE };
    esp_now_send(broadcast, pkt, sizeof(pkt));
}

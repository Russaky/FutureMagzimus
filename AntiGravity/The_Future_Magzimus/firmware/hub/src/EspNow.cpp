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
    if (len < 1) return;
    uint8_t groupId = data[0];
    if (groupId != GROUP_ID) return;

    if (len == sizeof(StaffTelemetry)) {
        SerialBridge::sendFrame(MSG_STAFF_TELEMETRY, data, (uint16_t)len);
    } else if (len == sizeof(MicTelemetry)) {
        SerialBridge::sendFrame(MSG_MIC_TELEMETRY, data, (uint16_t)len);
    } else if (len == sizeof(PedalEvent)) {
        const PedalEvent *ev = (const PedalEvent *)data;
        // double/triple reserved for system — forward all others
        SerialBridge::sendFrame(MSG_PEDAL_EVENT, data, (uint16_t)len);
    } else if (len == sizeof(IdentityResponse)) {
        const IdentityResponse *id = (const IdentityResponse *)data;
        if (id->marker != MSG_IDENTITY) return;
        SerialBridge::sendFrame(MSG_IDENTITY, data, (uint16_t)len);
    } else if (len == sizeof(AutonomousAnnounce)) {
        const AutonomousAnnounce *ann = (const AutonomousAnnounce *)data;
        if (ann->msgType != MSG_AUTONOMOUS) return;
        SerialBridge::sendFrame(MSG_AUTONOMOUS, data, (uint16_t)len);
    } else if (len == sizeof(PairingRequest)) {
        const PairingRequest *req = (const PairingRequest *)data;
        if (req->msgType != MSG_PAIR_REQ) return;
        SerialBridge::sendFrame(MSG_PAIR_REQ, data, (uint16_t)len);
        PairingAck ack = {};
        ack.groupId  = GROUP_ID;
        ack.msgType  = MSG_PAIR_ACK;
        ack.targetId = req->deviceId;
        memcpy(ack.hubMac, s_hubMac, 6);
        esp_now_send(broadcast, (const uint8_t *)&ack, sizeof(ack));
    } else if (len >= (int)sizeof(EffectListHeader)) {
        const EffectListHeader *hdr = (const EffectListHeader *)data;
        if (hdr->msgType == MSG_EFFECT_LIST)
            SerialBridge::sendFrame(MSG_EFFECT_LIST, data, (uint16_t)len);
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

// During Staff OTA, Hub joins the same real network as Staff (instead of hosting
// its own AP) so both land on that network's actual channel and ESP-NOW keeps
// working — Mac never has to leave its own network to reach the Staff for OTA.
#ifdef WIFI_SSID
static bool s_wifiJoined = false;

void EspNow::wifiJoin() {
    if (s_wifiJoined) return;
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    uint32_t t = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t < 10000)
        delay(100);
    if (WiFi.status() == WL_CONNECTED) {
        s_wifiJoined = true;
        Serial.printf("Hub joined %s  channel:%d  ip:%s\n",
                      WIFI_SSID, WiFi.channel(), WiFi.localIP().toString().c_str());
    } else {
        Serial.println("Hub WiFi join failed");
    }
}

void EspNow::wifiLeave() {
    if (!s_wifiJoined) return;
    WiFi.disconnect(true);
    s_wifiJoined = false;
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    Serial.println("Hub left WiFi — back on ESP-NOW channel");
}
#else
void EspNow::wifiJoin()  {}
void EspNow::wifiLeave() {}
#endif

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

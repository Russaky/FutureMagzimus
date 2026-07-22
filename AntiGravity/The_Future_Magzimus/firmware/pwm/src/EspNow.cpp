#include "EspNow.h"
#include "Config.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

#define ROLE_PWM 3

uint8_t EspNow::deviceId = 0;

static uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static QueueHandle_t rxQueue;

static void sendIdentity() {
    IdentityResponse resp = {};
    resp.groupId  = GROUP_ID;
    resp.marker   = MSG_IDENTITY;
    resp.deviceId = EspNow::deviceId;
    resp.role     = ROLE_PWM;
    strncpy(resp.firmware, FIRMWARE_VERSION, sizeof(resp.firmware) - 1);
    esp_now_send(broadcast, (const uint8_t *)&resp, sizeof(resp));
}

static volatile uint32_t s_lastShowCmdMs = 0;
static const uint8_t BRIDGE_MAC[6] = {0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF};

static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(light_cmd_t)) {
        light_cmd_t cmd;
        memcpy(&cmd, data, sizeof(cmd));
        if (cmd.targetId != 0 && cmd.targetId != EspNow::deviceId) return;

        bool isBridge = (memcmp(mac_addr, BRIDGE_MAC, 6) == 0);
        uint32_t now = millis();
        if (isBridge) {
            if (s_lastShowCmdMs > 0 && (now - s_lastShowCmdMs) < 5000) {
                return; // Ignored: Show Mode active
            }
        } else {
            s_lastShowCmdMs = now; // Set/extend Show Mode lock
        }

        xQueueSendFromISR(rxQueue, &cmd, nullptr);
    } else if (len == sizeof(DiscoverRequest)) {
        DiscoverRequest req;
        memcpy(&req, data, sizeof(req));
        if (req.groupId != GROUP_ID || req.marker != MSG_DISCOVER) return;
        sendIdentity();
    }
}

void EspNow::init() {
    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);

    deviceId = NODE_ID;

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, BRIDGE_MAC, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);

    rxQueue = xQueueCreate(QUEUE_SIZE, sizeof(light_cmd_t));
}

bool EspNow::dequeue(light_cmd_t &out) {
    return xQueueReceive(rxQueue, &out, 0) == pdTRUE;
}

void EspNow::sendAck(uint8_t w, uint8_t r, uint8_t g, uint8_t b) {
    light_ack_t ack = { deviceId, w, r, g, b };
    esp_now_send(BRIDGE_MAC, (const uint8_t *)&ack, sizeof(ack));
}

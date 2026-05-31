#include "EspNow.h"
#include "Config.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

#define ROLE_RELAY 2

uint8_t EspNow::deviceId = 0;

static uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static QueueHandle_t rxQueue;

static void sendIdentity() {
    IdentityResponse resp = {};
    resp.groupId  = GROUP_ID;
    resp.marker   = MSG_IDENTITY;
    resp.deviceId = EspNow::deviceId;
    resp.role     = ROLE_RELAY;
    strncpy(resp.firmware, FIRMWARE_VERSION, sizeof(resp.firmware) - 1);
    esp_now_send(broadcast, (const uint8_t *)&resp, sizeof(resp));
}

static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(RelayCommand)) {
        RelayCommand cmd;
        memcpy(&cmd, data, sizeof(cmd));
        if (cmd.groupId != GROUP_ID) return;
        if (cmd.targetId != 0xFF && cmd.targetId != EspNow::deviceId) return;
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

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    deviceId = mac[5];

    rxQueue = xQueueCreate(QUEUE_SIZE, sizeof(RelayCommand));
}

bool EspNow::dequeue(RelayCommand &out) {
    return xQueueReceive(rxQueue, &out, 0) == pdTRUE;
}

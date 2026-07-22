#include "EspNow.h"
#include "Config.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

#define ROLE_DMX 7

uint16_t EspNow::deviceId = 0;

static uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static QueueHandle_t rxQueue;
static volatile bool s_discoverPending = false;

static void sendIdentity() {
    IdentityResponse resp = {};
    resp.groupId  = GROUP_ID;
    resp.marker   = MSG_IDENTITY;
    resp.deviceId = EspNow::deviceId;
    resp.role     = ROLE_DMX;
    strncpy(resp.firmware, FIRMWARE_VERSION, sizeof(resp.firmware) - 1);
    esp_now_send(broadcast, (const uint8_t *)&resp, sizeof(resp));
}

// The ESP-NOW recv callback runs in the WiFi driver's task context — calling
// esp_now_send() synchronously from inside it is unreliable (this is why
// discover responses were silently lost under normal DMXCommand traffic:
// the send was racing the very radio stack that just invoked this callback).
// DMXCommand already avoided this via the ISR-safe queue; discover now does too.
static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(DMXCommand)) {
        DMXCommand cmd;
        memcpy(&cmd, data, sizeof(cmd));
        if (cmd.groupId != GROUP_ID) return;
        xQueueSendFromISR(rxQueue, &cmd, nullptr);
    } else if (len == sizeof(DiscoverRequest)) {
        DiscoverRequest req;
        memcpy(&req, data, sizeof(req));
        if (req.groupId != GROUP_ID || req.marker != MSG_DISCOVER) return;
        s_discoverPending = true;
    }
}

void EspNow::init() {
    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    deviceId = ((uint16_t)mac[4] << 8) | mac[5];

    // Required before esp_now_send() can target the broadcast address —
    // receiving broadcasts doesn't need a registered peer, but sending to one
    // does. Without this, sendIdentity() silently fails (ESP_ERR_ESPNOW_NOT_FOUND)
    // and the device never responds to discover, even though it receives fine.
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, broadcast, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);

    rxQueue = xQueueCreate(QUEUE_SIZE, sizeof(DMXCommand));
}

void EspNow::pollDiscover() {
    if (s_discoverPending) {
        s_discoverPending = false;
        sendIdentity();
    }
}

bool EspNow::dequeue(DMXCommand &out) {
    return xQueueReceive(rxQueue, &out, 0) == pdTRUE;
}

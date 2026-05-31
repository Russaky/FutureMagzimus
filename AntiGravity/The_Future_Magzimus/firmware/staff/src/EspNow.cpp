#include "EspNow.h"
#include "Config.h"
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include <string.h>

#define ROLE_STAFF 1

uint16_t EspNow::deviceId = 0;

static uint8_t broadcast[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static uint8_t s_hubMac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static bool    s_hubPeered = false;
static QueueHandle_t rxQueue;
static QueueHandle_t wifiQueue;
static QueueHandle_t roleQueue;
static QueueHandle_t pairAckQueue;
static QueueHandle_t syncQueue;
static volatile uint32_t s_lastAckMs = 0;

static void onSent(const uint8_t *, esp_now_send_status_t status) {
    // intentionally empty — isHubAlive() is driven solely by MSG_HUB_ALIVE reception
    (void)status;
}

static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(HubCommand)) {
        HubCommand cmd;
        memcpy(&cmd, data, sizeof(cmd));
        if (cmd.groupId != GROUP_ID) return;
        if (cmd.targetId != 0xFFFF && cmd.targetId != EspNow::deviceId) return;
        xQueueSendFromISR(rxQueue, &cmd, nullptr);
    } else if (len == sizeof(WifiCtrlCommand)) {
        WifiCtrlCommand wcmd;
        memcpy(&wcmd, data, sizeof(wcmd));
        if (wcmd.groupId != GROUP_ID) return;
        xQueueSendFromISR(wifiQueue, &wcmd, nullptr);
    } else if (len == sizeof(RoleCtrlCommand)) {
        RoleCtrlCommand rcmd;
        memcpy(&rcmd, data, sizeof(rcmd));
        if (rcmd.groupId != GROUP_ID || rcmd.msgType != MSG_ROLE_CTRL) return;
        if (rcmd.targetId != 0xFFFF && rcmd.targetId != EspNow::deviceId) return;
        xQueueSendFromISR(roleQueue, &rcmd, nullptr);
    } else if (len == sizeof(PairingAck)) {
        PairingAck ack;
        memcpy(&ack, data, sizeof(ack));
        if (ack.groupId != GROUP_ID || ack.msgType != MSG_PAIR_ACK) return;
        if (ack.targetId != 0xFFFF && ack.targetId != EspNow::deviceId) return;
        xQueueSendFromISR(pairAckQueue, &ack, nullptr);
    } else if (len == sizeof(SyncPacket)) {
        SyncPacket pkt;
        memcpy(&pkt, data, sizeof(pkt));
        if (pkt.groupId != GROUP_ID || pkt.msgType != MSG_SYNC) return;
        xQueueSendFromISR(syncQueue, &pkt, nullptr);
    } else if (len == 2) {
        uint8_t groupId = data[0], marker = data[1];
        if (groupId != GROUP_ID) return;
        if (marker == MSG_DISCOVER) {
            EspNow::sendIdentity();
        } else if (marker == MSG_HUB_ALIVE) {
            s_lastAckMs = millis();  // Hub is alive — update heartbeat
        }
    }
}

void EspNow::init() {
    WiFi.mode(WIFI_STA);
    // If already connected to AP (e.g. for OTA), skip manual channel set —
    // ESP-NOW will use the AP's channel automatically.
    if (WiFi.status() != WL_CONNECTED)
        esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);
    esp_now_register_send_cb(onSent);
    esp_wifi_set_max_tx_power(80);                              // 20 dBm
    esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_1M_L); // max range

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, broadcast, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    deviceId = ((uint16_t)mac[4] << 8) | mac[5];

    rxQueue      = xQueueCreate(QUEUE_SIZE, sizeof(HubCommand));
    wifiQueue    = xQueueCreate(4,          sizeof(WifiCtrlCommand));
    roleQueue    = xQueueCreate(4,          sizeof(RoleCtrlCommand));
    pairAckQueue = xQueueCreate(2,          sizeof(PairingAck));
    syncQueue    = xQueueCreate(4,          sizeof(SyncPacket));
}

void EspNow::setHubMac(const uint8_t *mac) {
    if (memcmp(mac, s_hubMac, 6) == 0) return;
    memcpy(s_hubMac, mac, 6);
    if (!s_hubPeered) {
        esp_now_peer_info_t peer = {};
        memcpy(peer.peer_addr, mac, 6);
        peer.channel = 0;
        peer.encrypt = false;
        if (esp_now_add_peer(&peer) == ESP_OK) s_hubPeered = true;
    }
    Serial.printf("Hub unicast peer set: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
}

void EspNow::sendTelemetry(const StaffTelemetry &pkt) {
    // unicast when paired (real ACK) → isHubAlive() works; broadcast otherwise
    esp_now_send(s_hubMac, (const uint8_t *)&pkt, sizeof(pkt));
}

void EspNow::sendIdentity() {
    IdentityResponse resp = {};
    resp.groupId  = GROUP_ID;
    resp.marker   = MSG_IDENTITY;
    resp.deviceId = deviceId;
    resp.role     = ROLE_STAFF;
    strncpy(resp.firmware, FIRMWARE_VERSION, sizeof(resp.firmware) - 1);
#ifdef WIFI_SSID
    if (WiFi.status() == WL_CONNECTED) {
        uint32_t ip = (uint32_t)WiFi.localIP();
        memcpy(resp.ip, &ip, 4);
    }
#endif
    esp_now_send(broadcast, (const uint8_t *)&resp, sizeof(resp));
}

bool EspNow::dequeueCommand(HubCommand &out) {
    return xQueueReceive(rxQueue, &out, 0) == pdTRUE;
}

bool EspNow::dequeueWifiCtrl(WifiCtrlCommand &out) {
    return xQueueReceive(wifiQueue, &out, 0) == pdTRUE;
}

bool EspNow::isHubAlive() {
    return s_lastAckMs > 0 && (millis() - s_lastAckMs) < HUB_TIMEOUT_MS;
}

bool EspNow::dequeueRoleCtrl(RoleCtrlCommand &out) {
    return xQueueReceive(roleQueue, &out, 0) == pdTRUE;
}

bool EspNow::dequeuePairingAck(PairingAck &out) {
    return xQueueReceive(pairAckQueue, &out, 0) == pdTRUE;
}

bool EspNow::dequeueSyncPacket(SyncPacket &out) {
    return xQueueReceive(syncQueue, &out, 0) == pdTRUE;
}

void EspNow::sendPairingRequest(uint8_t staffId) {
    PairingRequest req = {};
    req.groupId  = GROUP_ID;
    req.msgType  = MSG_PAIR_REQ;
    req.deviceId = deviceId;
    req.staffId  = staffId;
    esp_wifi_get_mac(WIFI_IF_STA, req.mac);
    esp_now_send(broadcast, (const uint8_t *)&req, sizeof(req));
}

void EspNow::sendAutonomous(uint8_t state) {
    AutonomousAnnounce ann = {};
    ann.groupId  = GROUP_ID;
    ann.msgType  = MSG_AUTONOMOUS;
    ann.deviceId = deviceId;
    ann.state    = state;
    esp_now_send(broadcast, (const uint8_t *)&ann, sizeof(ann));
}

void EspNow::sendSyncPacket(uint8_t cmdType, uint8_t r, uint8_t g, uint8_t b) {
    SyncPacket pkt = {};
    pkt.groupId  = GROUP_ID;
    pkt.msgType  = MSG_SYNC;
    pkt.masterId = deviceId;
    pkt.cmdType  = cmdType;
    pkt.r = r; pkt.g = g; pkt.b = b;
    esp_now_send(broadcast, (const uint8_t *)&pkt, sizeof(pkt));
}

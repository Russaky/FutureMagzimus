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
static QueueHandle_t effectQueue;
static QueueHandle_t effectSyncQueue;
static volatile uint32_t s_lastAckMs = 0;

static void onSent(const uint8_t *, esp_now_send_status_t status) {
    // intentionally empty — isHubAlive() is driven solely by MSG_HUB_ALIVE reception
    (void)status;
}

static void onRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    // SyncPacket and HubCommand are both 8 bytes — disambiguate by msgType
    // marker (offset 1) before falling through to the generic HubCommand match.
    if (len == sizeof(SyncPacket) && data[1] == MSG_SYNC) {
        SyncPacket pkt;
        memcpy(&pkt, data, sizeof(pkt));
        if (pkt.groupId != GROUP_ID) return;
        xQueueSendFromISR(syncQueue, &pkt, nullptr);
    // EffectCommand/EffectSyncPacket — checked explicitly by msgType, before
    // any size-only fallback branch (same guard pattern as the SyncPacket
    // check above; see 2026-06-08 postmortem in DONE.md on relying on size
    // alone). Sizes grew (19/17 bytes) when custom RGB colors were added —
    // still msgType-guarded, not size-only, so this stays safe.
    } else if (len == sizeof(EffectCommand) && data[1] == MSG_CMD_EFFECT) {
        EffectCommand cmd;
        memcpy(&cmd, data, sizeof(cmd));
        if (cmd.groupId != GROUP_ID) return;
        if (cmd.targetId != 0xFFFF && cmd.targetId != EspNow::deviceId) return;
        xQueueSendFromISR(effectQueue, &cmd, nullptr);
    } else if (len == sizeof(EffectSyncPacket) && data[1] == MSG_SYNC_EFFECT) {
        EffectSyncPacket pkt;
        memcpy(&pkt, data, sizeof(pkt));
        if (pkt.groupId != GROUP_ID) return;
        xQueueSendFromISR(effectSyncQueue, &pkt, nullptr);
    } else if (len == sizeof(HubCommand)) {
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

    rxQueue         = xQueueCreate(QUEUE_SIZE, sizeof(HubCommand));
    wifiQueue       = xQueueCreate(4,          sizeof(WifiCtrlCommand));
    roleQueue       = xQueueCreate(4,          sizeof(RoleCtrlCommand));
    pairAckQueue    = xQueueCreate(2,          sizeof(PairingAck));
    syncQueue       = xQueueCreate(4,          sizeof(SyncPacket));
    effectQueue     = xQueueCreate(QUEUE_SIZE, sizeof(EffectCommand));
    effectSyncQueue = xQueueCreate(4,          sizeof(EffectSyncPacket));
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

bool EspNow::dequeueEffectCommand(EffectCommand &out) {
    return xQueueReceive(effectQueue, &out, 0) == pdTRUE;
}

bool EspNow::dequeueEffectSyncPacket(EffectSyncPacket &out) {
    return xQueueReceive(effectSyncQueue, &out, 0) == pdTRUE;
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

void EspNow::sendEffectSyncPacket(uint8_t templateId, uint8_t paletteId, uint8_t speed,
                                   uint8_t intensity, uint8_t param1, uint8_t param2,
                                   uint8_t colorMode, uint8_t pr, uint8_t pg, uint8_t pb,
                                   uint8_t sr, uint8_t sg, uint8_t sb) {
    EffectSyncPacket pkt = {};
    pkt.groupId    = GROUP_ID;
    pkt.msgType    = MSG_SYNC_EFFECT;
    pkt.masterId   = deviceId;
    pkt.templateId = templateId;
    pkt.paletteId  = paletteId;
    pkt.speed      = speed;
    pkt.intensity  = intensity;
    pkt.param1     = param1;
    pkt.param2     = param2;
    pkt.colorMode  = colorMode;
    pkt.pr = pr; pkt.pg = pg; pkt.pb = pb;
    pkt.sr = sr; pkt.sg = sg; pkt.sb = sb;
    esp_now_send(broadcast, (const uint8_t *)&pkt, sizeof(pkt));
}

void EspNow::sendEffectList() {
    // Staff supports these LED effects — announced once at boot.
    // IDs 0-5 = fixed CmdType effects (unchanged, still used outside the
    // Effects Lab UI e.g. onboarding.html). IDs 6-13 = generic FastLED-based
    // templates (EffectTemplate, sent via MSG_CMD_EFFECT) — offset by 6 so
    // Mac-side can tell the two families apart.
    static const struct { uint8_t id; const char name[8]; } effects[] = {
        {0, "OFF"},
        {1, "SOLID"},
        {2, "SPARKLE"},
        {3, "FLAME"},
        {4, "RAINBOW"},
        {5, "TILT"},
        {6,  "GSOLID"},
        {7,  "GRAD"},
        {8,  "WAVE"},
        {9,  "FADE"},
        {10, "GSPARK"},
        {11, "CHASE"},
        {12, "FLAME2"},
        {13, "VERT"},
    };
    constexpr uint8_t N = sizeof(effects)/sizeof(effects[0]);
    // Build packet: header(5) + N * 9 bytes
    uint8_t buf[5 + N * 9];
    buf[0] = GROUP_ID;
    buf[1] = MSG_EFFECT_LIST;
    buf[2] = (uint8_t)(deviceId & 0xFF);
    buf[3] = (uint8_t)(deviceId >> 8);
    buf[4] = N;
    for (int i = 0; i < N; i++) {
        buf[5 + i*9]     = effects[i].id;
        memcpy(&buf[6 + i*9], effects[i].name, 8);
    }
    esp_now_send(broadcast, buf, sizeof(buf));
}

void EspNow::sendPWMCommand(uint8_t targetId, uint8_t w, uint8_t r, uint8_t g, uint8_t b, uint16_t fadeMs) {
    PWMCommand cmd;
    cmd.groupId  = GROUP_ID;
    cmd.targetId = targetId;
    cmd.w        = w;
    cmd.r        = r;
    cmd.g        = g;
    cmd.b        = b;
    cmd.fadeMs   = fadeMs;
    esp_now_send(broadcast, (const uint8_t *)&cmd, sizeof(cmd));
}

void EspNow::sendDMXCommand(uint16_t targetAddr, uint8_t w, uint8_t r, uint8_t g, uint8_t b) {
    DMXCommand cmd;
    cmd.groupId    = GROUP_ID;
    cmd.targetAddr = targetAddr;
    cmd.w = w; cmd.r = r; cmd.g = g; cmd.b = b;
    esp_now_send(broadcast, (const uint8_t *)&cmd, sizeof(cmd));
}

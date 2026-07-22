#include <Arduino.h>
#include <FastLED.h>
#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include "Config.h"
#include "Protocol.h"

static CRGB leds[NUM_LEDS];
static uint8_t s_deviceId = 0;
static uint8_t s_broadcastMac[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

// Current display state
static uint8_t s_mode       = 0;    // 0=progress, 1=solid
static uint8_t s_value      = 0;    // 0-100 for progress
static uint8_t s_r=0, s_g=0, s_b=0;
static uint16_t s_fadeMs    = 0;
static uint32_t s_fadeStart = 0;
static uint8_t s_prevValue  = 0;    // for lerp during fade

// Incoming queue
static volatile bool s_cmdPending = false;
static ProgressCommand s_pendingCmd;

static void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
    if (len == sizeof(ProgressCommand)) {
        const ProgressCommand *cmd = (const ProgressCommand *)data;
        if (cmd->groupId != GROUP_ID) return;
        if (cmd->targetId != 0xFF && cmd->targetId != s_deviceId) return;
        s_pendingCmd  = *cmd;
        s_cmdPending  = true;
    } else if (len == 2) {
        // DiscoverRequest
        const DiscoverRequest *req = (const DiscoverRequest *)data;
        if (req->groupId != GROUP_ID || req->marker != MSG_DISCOVER) return;
        IdentityResponse resp = {};
        resp.groupId  = GROUP_ID;
        resp.marker   = MSG_IDENTITY;
        resp.deviceId = s_deviceId;
        resp.role     = ROLE_PROGRESS_BAR;
        strncpy(resp.firmware, FIRMWARE_VERSION, 8);
        esp_now_send(s_broadcastMac, (const uint8_t *)&resp, sizeof(resp));
    } else if (len == sizeof(WifiCtrlCommand)) {
        const WifiCtrlCommand *wc = (const WifiCtrlCommand *)data;
        if (wc->groupId != GROUP_ID) return;
        if (wc->targetId != 0xFFFF && wc->targetId != s_deviceId) return;
        // WiFi OTA not implemented in this MVP
    }
}

static void applyCommand(const ProgressCommand &cmd) {
    s_mode     = cmd.mode;
    s_r        = cmd.r;
    s_g        = cmd.g;
    s_b        = cmd.b;
    s_fadeMs   = cmd.fadeMs;
    s_fadeStart = millis();
    s_prevValue = s_value;
    s_value    = (cmd.mode == 0) ? cmd.value : 100;
}

static void renderLeds() {
    // Compute effective value with fade
    uint8_t effValue = s_value;
    if (s_fadeMs > 0) {
        uint32_t elapsed = millis() - s_fadeStart;
        if (elapsed < s_fadeMs) {
            float t = (float)elapsed / (float)s_fadeMs;
            effValue = (uint8_t)(s_prevValue + t * ((float)s_value - s_prevValue));
        }
    }

    if (s_mode == 0) {
        // Progress bar: fill from left
        uint8_t litCount = (uint8_t)((effValue * NUM_LEDS + 50) / 100);
        for (int i = 0; i < NUM_LEDS; i++) {
            leds[i] = (i < litCount) ? CRGB(s_r, s_g, s_b) : CRGB::Black;
        }
    } else {
        // Solid color
        fill_solid(leds, NUM_LEDS, CRGB(s_r, s_g, s_b));
    }
    FastLED.show();
}

void setup() {
    Serial.begin(115200);
    FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS);
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    FastLED.clear(true);

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);

    // Use last 2 bytes of MAC as deviceId
    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    s_deviceId = (uint8_t)((mac[4] << 4) | (mac[5] & 0x0F));

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, s_broadcastMac, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);

    Serial.printf("ProgressBar ready  ID:%02X  FW:%s\n", s_deviceId, FIRMWARE_VERSION);
}

void loop() {
    if (s_cmdPending) {
        s_cmdPending = false;
        applyCommand(s_pendingCmd);
    }
    renderLeds();
    delay(16);  // ~60 FPS
}

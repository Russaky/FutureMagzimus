#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include "Config.h"
#include "Protocol.h"

static uint16_t s_deviceId = 0;
static uint8_t  s_broadcastMac[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

// ─── Button state machine ──────────────────────────────────────────────────────
static bool     s_lastPhysical = HIGH;  // INPUT_PULLUP: HIGH=released
static bool     s_pressed      = false;
static uint32_t s_pressedAt    = 0;
static uint32_t s_releasedAt   = 0;
static uint8_t  s_tapCount     = 0;     // counts rapid taps for double/triple
static uint32_t s_lastTapMs    = 0;

static void sendEvent(uint8_t evType) {
    PedalEvent ev = {};
    ev.groupId   = GROUP_ID;
    ev.deviceId  = s_deviceId;
    ev.eventType = evType;
    esp_now_send(s_broadcastMac, (const uint8_t *)&ev, sizeof(ev));
    Serial.printf("Pedal event: %d\n", evType);
}

static void setLed(uint8_t status) {
    digitalWrite(STATUS_LED_RED_PIN,    LOW);
    digitalWrite(STATUS_LED_GREEN_PIN,  LOW);
    digitalWrite(STATUS_LED_YELLOW_PIN, LOW);
    switch (status) {
        case NET_STATUS_NO_BRAIN: digitalWrite(STATUS_LED_RED_PIN,    HIGH); break;
        case NET_STATUS_MISSING:  digitalWrite(STATUS_LED_YELLOW_PIN, HIGH); break;
        case NET_STATUS_OK:       digitalWrite(STATUS_LED_GREEN_PIN,  HIGH); break;
    }
}

static void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
    if (len == sizeof(NetStatusCommand)) {
        const NetStatusCommand *cmd = (const NetStatusCommand *)data;
        if (cmd->groupId != GROUP_ID) return;
        if (cmd->targetId != 0xFF && cmd->targetId != (uint8_t)s_deviceId) return;
        setLed(cmd->status);
    } else if (len == 2) {
        const DiscoverRequest *req = (const DiscoverRequest *)data;
        if (req->groupId != GROUP_ID || req->marker != MSG_DISCOVER) return;
        IdentityResponse resp = {};
        resp.groupId  = GROUP_ID;
        resp.marker   = MSG_IDENTITY;
        resp.deviceId = s_deviceId;
        resp.role     = ROLE_PEDAL;
        strncpy(resp.firmware, FIRMWARE_VERSION, 8);
        esp_now_send(s_broadcastMac, (const uint8_t *)&resp, sizeof(resp));
    }
}

void setup() {
    Serial.begin(115200);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    pinMode(STATUS_LED_RED_PIN,    OUTPUT);
    pinMode(STATUS_LED_GREEN_PIN,  OUTPUT);
    pinMode(STATUS_LED_YELLOW_PIN, OUTPUT);
    setLed(NET_STATUS_NO_BRAIN);  // red until network confirmed

    WiFi.mode(WIFI_STA);
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
    esp_now_init();
    esp_now_register_recv_cb(onRecv);

    uint8_t mac[6];
    esp_wifi_get_mac(WIFI_IF_STA, mac);
    s_deviceId = (uint16_t)((mac[4] << 8) | mac[5]);

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, s_broadcastMac, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    esp_now_add_peer(&peer);

    Serial.printf("Pedal ready  ID:%04X  FW:%s\n", s_deviceId, FIRMWARE_VERSION);
}

void loop() {
    uint32_t now    = millis();
    bool physical   = digitalRead(BUTTON_PIN);  // HIGH=released (pullup)
    bool debounced  = physical;

    // Debounce
    static uint32_t lastChangeMs = 0;
    static bool     lastStable   = HIGH;
    if (physical != s_lastPhysical) {
        lastChangeMs   = now;
        s_lastPhysical = physical;
    }
    if (now - lastChangeMs >= DEBOUNCE_MS) {
        debounced = s_lastPhysical;
    } else {
        debounced = lastStable;
    }
    lastStable = debounced;

    bool isPressed = (debounced == LOW);

    // Detect press transition
    if (isPressed && !s_pressed) {
        s_pressed   = true;
        s_pressedAt = now;
        sendEvent(PEDAL_PRESS);
    }

    // Detect release transition
    if (!isPressed && s_pressed) {
        s_pressed     = false;
        s_releasedAt  = now;
        uint32_t held = s_releasedAt - s_pressedAt;
        sendEvent(PEDAL_RELEASE);

        if (held >= LONG_THRESHOLD_MS) {
            // Long press — emit immediately, skip tap counting
            sendEvent(PEDAL_LONG);
            s_tapCount = 0;
        } else {
            // Short release — accumulate tap count for double/triple detection
            s_tapCount++;
            s_lastTapMs = now;
        }
    }

    // Flush tap count after timeout
    if (s_tapCount > 0 && !s_pressed && (now - s_lastTapMs > DOUBLE_WINDOW_MS)) {
        if (s_tapCount >= 3) {
            sendEvent(PEDAL_TRIPLE);
        } else if (s_tapCount == 2) {
            sendEvent(PEDAL_DOUBLE);
        } else {
            sendEvent(PEDAL_SHORT);
        }
        s_tapCount = 0;
    }
}

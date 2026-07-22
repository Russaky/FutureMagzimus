#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_now.h>
#include <esp_wifi.h>
#include "Config.h"
#include "Protocol.h"
#include "credentials.h"

WebServer server(80);
static uint8_t s_broadcastMac[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

// Simplified phone console — no frameworks, no build step.
const char INDEX_HTML[] PROGMEM = R"rawliteral(
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MAGZIMUS Lights</title>
<style>
body { font-family: sans-serif; background:#111; color:#eee; padding:10px; }
.row { border:1px solid #444; border-radius:8px; padding:10px; margin-bottom:10px; }
.row label { font-weight:bold; display:block; margin-bottom:6px; }
.row input[type=range] { width:100%; }
.row button { width:100%; padding:10px; margin-top:8px; background:#ff5e00; color:#fff; border:none; border-radius:6px; font-weight:bold; }
</style>
</head>
<body>
<h2>MAGZIMUS Lights</h2>
<div id="rows"></div>
<script>
const names = ["הכל", "פנס 1", "פנס 2", "פנס 3", "פנס 4"];
const rows = document.getElementById('rows');
names.forEach((name, target) => {
    const row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = `
        <label>${name}</label>
        R <input type="range" min="0" max="255" value="0" id="r${target}">
        G <input type="range" min="0" max="255" value="0" id="g${target}">
        B <input type="range" min="0" max="255" value="0" id="b${target}">
        W <input type="range" min="0" max="255" value="0" id="w${target}">
        <button onclick="send(${target})">SEND</button>
    `;
    rows.appendChild(row);
});

function send(target) {
    const body = {
        target: target,
        r: parseInt(document.getElementById('r' + target).value),
        g: parseInt(document.getElementById('g' + target).value),
        b: parseInt(document.getElementById('b' + target).value),
        w: parseInt(document.getElementById('w' + target).value)
    };
    fetch('/color', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).catch(err => console.error('Send failed:', err));
}
</script>
</body>
</html>
)rawliteral";

// ─── ACK timeout tracking (per node 1-4) ─────────────────────────────────────
struct PendingAck {
    bool waiting;
    uint32_t sentAt;
};
static PendingAck s_pending[5]; // index 1..4, [0] unused

static void trackSend(uint8_t target) {
    uint32_t now = millis();
    if (target == 0) {
        for (uint8_t i = 1; i <= 4; i++) {
            s_pending[i].waiting = true;
            s_pending[i].sentAt = now;
        }
    } else if (target >= 1 && target <= 4) {
        s_pending[target].waiting = true;
        s_pending[target].sentAt = now;
    }
}

static void checkAckTimeouts() {
    uint32_t now = millis();
    for (uint8_t i = 1; i <= 4; i++) {
        if (s_pending[i].waiting && (now - s_pending[i].sentAt) >= 200) {
            s_pending[i].waiting = false;
            Serial.printf("[TIMEOUT] Node %d\n", i);
        }
    }
}

// ─── ESP-NOW ACK reception (callback only buffers — work happens in loop) ───
static light_ack_t s_lastAck;
static volatile bool s_hasAck = false;

static void onEspNowRecv(const uint8_t *mac_addr, const uint8_t *data, int len) {
    if (len == sizeof(light_ack_t)) {
        memcpy(&s_lastAck, data, sizeof(light_ack_t));
        s_hasAck = true;
    }
}

static void processAcks() {
    if (!s_hasAck) return;
    s_hasAck = false;
    light_ack_t ack = s_lastAck;
    Serial.printf("[ACK] Node %d: R=%d G=%d B=%d W=%d\n", ack.nodeId, ack.r, ack.g, ack.b, ack.w);
    if (ack.nodeId >= 1 && ack.nodeId <= 4) {
        s_pending[ack.nodeId].waiting = false;
    }
}

// ─── Shared command dispatch (HTTP + Serial JSON share this) ────────────────
static void sendColor(uint8_t target, uint8_t r, uint8_t g, uint8_t b, uint8_t w) {
    light_cmd_t cmd;
    cmd.targetId = target;
    cmd.w        = w;
    cmd.r        = r;
    cmd.g        = g;
    cmd.b        = b;

    esp_err_t res = esp_now_send(s_broadcastMac, (const uint8_t *)&cmd, sizeof(cmd));
    trackSend(target);

    Serial.printf("Bridge ESP-NOW send target:%d  R:%d G:%d B:%d W:%d  res:%s\n",
                  target, r, g, b, w, (res == ESP_OK) ? "OK" : "FAIL");
}

// Minimal JSON field extraction — avoids pulling in a full JSON library.
static int extractIntField(const String &body, const char *key) {
    String pattern = String("\"") + key + "\":";
    int idx = body.indexOf(pattern);
    if (idx == -1) return 0;
    return body.substring(idx + pattern.length()).toInt();
}

static void dispatchColorJson(const String &body) {
    uint8_t target = (uint8_t)extractIntField(body, "target");
    uint8_t r       = (uint8_t)extractIntField(body, "r");
    uint8_t g       = (uint8_t)extractIntField(body, "g");
    uint8_t b       = (uint8_t)extractIntField(body, "b");
    uint8_t w       = (uint8_t)extractIntField(body, "w");
    sendColor(target, r, g, b, w);
}

// ─── HTTP ─────────────────────────────────────────────────────────────────
void handleRoot() {
    server.send(200, "text/html", INDEX_HTML);
}

void handleColor() {
    if (server.method() != HTTP_POST) {
        server.send(405, "application/json", "{\"error\":\"Method not allowed\"}");
        return;
    }
    dispatchColorJson(server.arg("plain"));
    server.send(200, "application/json", "{\"status\":\"ok\"}");
}

// ─── Serial JSON interface ───────────────────────────────────────────────
static void pollSerial() {
    static String line;
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            if (line.length() > 0) {
                dispatchColorJson(line);
                line = "";
            }
        } else if (c != '\r') {
            line += c;
        }
    }
}

void setup() {
    Serial.begin(115200);

    WiFi.mode(WIFI_AP_STA);

    // Set custom Bridge MAC address (crucial for source preemption/locking)
    uint8_t customMac[6] = BRIDGE_MAC_ADDR;
    esp_wifi_set_mac(WIFI_IF_STA, customMac);

    // AP on a fixed channel — its only job is to lock the radio on ESPNOW_CHANNEL.
    WiFi.softAP(AP_SSID, AP_PASSWORD, ESPNOW_CHANNEL);
    Serial.printf("[BOOT] AP started: %s  IP: %s  Channel: %d\n",
                  AP_SSID, WiFi.softAPIP().toString().c_str(), ESPNOW_CHANNEL);

    // Try known networks in order, each with its own timeout and static IP.
    bool connected = false;
    for (uint8_t i = 0; i < WIFI_NETWORK_COUNT; i++) {
        const WifiNetwork &net = WIFI_NETWORKS[i];
        if (net.ssid[0] == '\0') continue;

        Serial.printf("[BOOT] Trying network %d: %s\n", i, net.ssid);
        WiFi.begin(net.ssid, net.password);
        if (WiFi.waitForConnectResult(WIFI_NETWORK_TIMEOUT_MS) == WL_CONNECTED) {
            WiFi.config(net.ip, net.gateway, net.subnet);
            Serial.printf("[BOOT] Connected to %s, IP: %s\n",
                          net.ssid, WiFi.localIP().toString().c_str());
            connected = true;
            break;
        }
        WiFi.disconnect();
    }
    if (!connected) {
        Serial.println("[BOOT] No network found, AP mode only");
    }

    // Lock channel explicitly for the STA/ESP-NOW interface.
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);

    // Init ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("ESP-NOW init failed!");
        return;
    }
    esp_now_register_recv_cb(onEspNowRecv);

    esp_wifi_set_max_tx_power(80); // 20 dBm (max)
    esp_wifi_config_espnow_rate(WIFI_IF_STA, WIFI_PHY_RATE_1M_L); // Long range

    // Add broadcast peer
    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, s_broadcastMac, 6);
    peer.channel = ESPNOW_CHANNEL;
    peer.encrypt = false;
    if (esp_now_add_peer(&peer) != ESP_OK) {
        Serial.println("Failed to add broadcast peer!");
    }

    // Configure Web Routes
    server.on("/", HTTP_GET, handleRoot);
    server.on("/color", HTTP_POST, handleColor);
    server.begin();

    uint8_t currentMac[6];
    esp_wifi_get_mac(WIFI_IF_STA, currentMac);
    Serial.printf("Bridge MAC: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  currentMac[0], currentMac[1], currentMac[2],
                  currentMac[3], currentMac[4], currentMac[5]);
    Serial.printf("[BOOT] Bridge ready, channel=%d\n", ESPNOW_CHANNEL);
}

void loop() {
    server.handleClient();
    pollSerial();
    processAcks();
    checkAckTimeouts();
    delay(2);
}

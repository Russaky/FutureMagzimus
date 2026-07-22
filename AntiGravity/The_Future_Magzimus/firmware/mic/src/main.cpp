#include <Arduino.h>
#include <esp_now.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <arduinoFFT.h>
#include "Config.h"
#include "Protocol.h"
#include "SerialBridge.h"

static uint16_t s_deviceId = 0;
static uint8_t  s_broadcastMac[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};

// ADC sampling
static uint32_t s_sampleInterval = 1000000UL / SAMPLE_RATE;  // µs
static uint32_t s_lastSampleUs   = 0;
static uint16_t s_sampleIdx      = 0;

static double s_real[FFT_WINDOW_SIZE];
static double s_imag[FFT_WINDOW_SIZE];

static float s_rms       = 0.0f;
static float s_peak      = 0.0f;
static float s_frequency = 0.0f;

static uint32_t s_lastTelemetryMs = 0;

static ArduinoFFT<double> s_fft(s_real, s_imag, FFT_WINDOW_SIZE, (double)SAMPLE_RATE);

static void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
    if (len == 2) {
        const DiscoverRequest *req = (const DiscoverRequest *)data;
        if (req->groupId != GROUP_ID || req->marker != MSG_DISCOVER) return;
        IdentityResponse resp = {};
        resp.groupId  = GROUP_ID;
        resp.marker   = MSG_IDENTITY;
        resp.deviceId = s_deviceId;
        resp.role     = ROLE_MIC;
        strncpy(resp.firmware, FIRMWARE_VERSION, 8);
        esp_now_send(s_broadcastMac, (const uint8_t *)&resp, sizeof(resp));
    }
}

static void processWindow() {
    // DC removal and RMS/peak calculation
    double sum = 0;
    for (int i = 0; i < FFT_WINDOW_SIZE; i++) sum += s_real[i];
    double mean = sum / FFT_WINDOW_SIZE;

    double rmsSum = 0;
    float  peak   = 0;
    for (int i = 0; i < FFT_WINDOW_SIZE; i++) {
        double v = s_real[i] - mean;
        s_real[i] = v;
        s_imag[i] = 0;
        rmsSum += v * v;
        float absV = fabsf((float)v);
        if (absV > peak) peak = absV;
    }

    // Normalize to 0-1 range (12-bit ADC → 4095 max)
    s_rms  = sqrtf((float)(rmsSum / FFT_WINDOW_SIZE)) / 4095.0f;
    s_peak = peak / 4095.0f;

    // FFT for dominant frequency
    s_fft.windowing(FFTWindow::Hamming, FFTDirection::Forward);
    s_fft.compute(FFTDirection::Forward);
    s_fft.complexToMagnitude();
    s_frequency = (float)s_fft.majorPeak();

    s_sampleIdx = 0;
}

void setup() {
    SerialBridge::begin(115200, nullptr);
    analogReadResolution(12);
    analogSetAttenuation(ADC_11db);  // full 3.3V range

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

    Serial.printf("Mic ready  ID:%04X  FW:%s\n", s_deviceId, FIRMWARE_VERSION);
}

void loop() {
    uint32_t nowUs = micros();
    if (nowUs - s_lastSampleUs >= s_sampleInterval) {
        s_lastSampleUs = nowUs;
        s_real[s_sampleIdx] = (double)analogRead(MIC_ADC_PIN);
        s_sampleIdx++;
        if (s_sampleIdx >= FFT_WINDOW_SIZE) {
            processWindow();
        }
    }

    uint32_t nowMs = millis();
    if (nowMs - s_lastTelemetryMs >= TELEMETRY_MS) {
        s_lastTelemetryMs = nowMs;
        MicTelemetry pkt = {};
        pkt.groupId   = GROUP_ID;
        pkt.deviceId  = s_deviceId;
        pkt.rms       = s_rms;
        pkt.peak      = s_peak;
        pkt.frequency = s_frequency;

        // DEV/PRODUCTION hierarchy (microphone_spec.md §2.3): ESP-NOW is the
        // default; a live USB CDC host connection (real terminal, not just a
        // power source like a power bank) overrides it and the same framed
        // telemetry goes out over USB Serial instead.
        if (Serial.isConnected()) {
            SerialBridge::sendFrame(MSG_MIC_TELEMETRY, (const uint8_t *)&pkt, sizeof(pkt));
        } else {
            esp_now_send(s_broadcastMac, (const uint8_t *)&pkt, sizeof(pkt));
        }
    }
}

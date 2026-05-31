#include <Arduino.h>
#include <Preferences.h>
#include "Config.h"
#include "Protocol.h"
#include "EspNow.h"
#include "ImuManager.h"
#include "LedManager.h"
#ifdef WIFI_SSID
#include <WiFi.h>
#include <ArduinoOTA.h>

#define WIFI_AUTO_OFF_MS (2UL * 60 * 1000)   // 2 min — faster recovery if OTA fails

static bool     wifiActive       = false;
static uint32_t wifiEnabledAt    = 0;

static void wifiDisable() {
    if (!wifiActive) return;
    ArduinoOTA.end();
    WiFi.disconnect(true);
    wifiActive = false;
    Serial.println("WiFi OFF");
}

static void wifiEnable() {
    if (wifiActive) return;
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    uint32_t t = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t < 10000)
        delay(100);
    if (WiFi.status() == WL_CONNECTED) {
        ArduinoOTA.setHostname(OTA_HOSTNAME);
        ArduinoOTA.setPassword(OTA_PASSWORD);
        ArduinoOTA.onError([](ota_error_t e) {
            Serial.printf("OTA error %u — disabling WiFi\n", e);
            wifiDisable();  // auto-recover on OTA failure
        });
        ArduinoOTA.begin();
        wifiActive    = true;
        wifiEnabledAt = millis();
        EspNow::sendIdentity();
        Serial.printf("WiFi ON  host:%s  ip:%s\n",
                      OTA_HOSTNAME, WiFi.localIP().toString().c_str());
    } else {
        Serial.println("WiFi failed");
    }
}
#endif

static uint32_t lastTelemetryMs = 0;
static bool     cmdOverride      = false;
static float    lastAngle        = 0.0f;
static bool     sparkleActive    = false;
static uint8_t  sparkleR=255, sparkleG=255, sparkleB=255, sparkleDensity=128;
static bool     flameActive      = false;
static bool     rainbowActive    = false;
static bool     imuOk            = false;
static bool     g_txEnabled      = true;
static bool     g_hubWasAlive    = false;  // tracks previous Hub alive state

// Dual-head slave state machine
static bool     g_slaveMode      = false;  // true when g_txEnabled==false
static uint32_t lastSyncMs       = 0;
static bool     slaveSynced      = false;

// NVS helpers
static void loadRole() {
    Preferences prefs;
    prefs.begin("staff", true);
    g_txEnabled = prefs.getBool("tx_en", true);
    prefs.end();
    g_slaveMode = !g_txEnabled;
}

static void saveRole(bool txEnabled) {
    Preferences prefs;
    prefs.begin("staff", false);
    prefs.putBool("tx_en", txEnabled);
    prefs.end();
}

static uint8_t loadStaffId() {
    Preferences prefs;
    prefs.begin("staff", true);
    uint8_t id = prefs.getUChar("staff_id", 0);
    prefs.end();
    return id;
}

void setup() {
    Serial.begin(115200);
    loadRole();
    EspNow::init();
    LedManager::init();
    imuOk = ImuManager::init();
    if (!imuOk) Serial.println("IMU init failed");
    uint8_t staffId = loadStaffId();
    EspNow::sendPairingRequest(staffId);
    Serial.printf("Staff ready — ID: %04X  FW: %s  tx: %s  staffId: %d\n",
                  EspNow::deviceId, FIRMWARE_VERSION,
                  g_txEnabled ? "enabled" : "disabled", staffId);
}

void loop() {
    uint32_t now = millis();

#ifdef WIFI_SSID
    if (wifiActive) {
        ArduinoOTA.handle();
        if (now - wifiEnabledAt >= WIFI_AUTO_OFF_MS)
            wifiDisable();
    }
#endif

    if (now - lastTelemetryMs >= TELEMETRY_MS) {
        lastTelemetryMs = now;
        ImuData imu;
        if (ImuManager::read(imu)) {
            lastAngle = imu.angle;
            if (g_txEnabled) {
                StaffTelemetry pkt = {};
                pkt.groupId    = GROUP_ID;
                pkt.deviceId   = EspNow::deviceId;
                pkt.speed      = imu.speed;
                pkt.angle      = imu.angle;
                pkt.accX       = imu.accX;
                pkt.accY       = imu.accY;
                pkt.accZ       = imu.accZ;
                pkt.gyroX      = imu.gyroX;
                pkt.gyroY      = imu.gyroY;
                pkt.gyroZ      = imu.gyroZ;
                pkt.motionType = MOTION_IDLE;
                EspNow::sendTelemetry(pkt);
            }
        }

        // Master: send sync to slave every telemetry cycle
        if (g_txEnabled) {
            uint8_t tiltHue = (uint8_t)(((lastAngle + 90.0f) / 180.0f) * 170.0f);
            uint8_t sc = cmdOverride ? (flameActive ? CMD_LED_FLAME :
                                        rainbowActive ? CMD_LED_RAINBOW :
                                        sparkleActive ? CMD_LED_SPARKLE : CMD_LED_SOLID)
                                     : CMD_LED_TILT;
            uint8_t sr = cmdOverride ? (sparkleActive ? sparkleR : 0) : tiltHue;
            uint8_t sg = cmdOverride ? (sparkleActive ? sparkleG : 0) : 0;
            uint8_t sb = cmdOverride ? (sparkleActive ? sparkleB : 0) : 0;
            EspNow::sendSyncPacket(sc, sr, sg, sb);
        }

        bool hubAlive = EspNow::isHubAlive();
        if (hubAlive && !g_hubWasAlive) {
            g_hubWasAlive = true;
            EspNow::sendAutonomous(1);  // Hub restored
            Serial.println("Hub restored — following commands");
        } else if (!hubAlive && g_hubWasAlive) {
            g_hubWasAlive = false;
            cmdOverride = false;
            EspNow::sendAutonomous(0);  // Hub lost → autonomous
            Serial.println("Hub lost — autonomous mode");
        }

        if (!cmdOverride || !hubAlive) {
            cmdOverride    = false;
            sparkleActive  = false;
            flameActive    = false;
            rainbowActive  = false;
            LedManager::tilt(lastAngle);
        } else if (rainbowActive) {
            LedManager::rainbow();
        } else if (flameActive) {
            LedManager::flame();
        } else if (sparkleActive) {
            LedManager::sparkle(sparkleR, sparkleG, sparkleB, sparkleDensity);
        }
    }

    HubCommand cmd;
    while (EspNow::dequeueCommand(cmd)) {
        switch (cmd.cmdType) {
            case CMD_LED_SOLID:
                LedManager::solid(cmd.r, cmd.g, cmd.b, cmd.brightness);
                cmdOverride   = true;
                sparkleActive = false;
                break;
            case CMD_LED_SPARKLE:
                sparkleR       = cmd.r;
                sparkleG       = cmd.g;
                sparkleB       = cmd.b;
                sparkleDensity = cmd.brightness;
                cmdOverride    = true;
                sparkleActive  = true;
                flameActive    = false;
                break;
            case CMD_LED_FLAME:
                cmdOverride   = true;
                flameActive   = true;
                sparkleActive = false;
                rainbowActive = false;
                break;
            case CMD_LED_RAINBOW:
                cmdOverride   = true;
                rainbowActive = true;
                flameActive   = false;
                sparkleActive = false;
                break;
            case CMD_LED_OFF:
                LedManager::off();
                cmdOverride   = false;
                sparkleActive = false;
                flameActive   = false;
                rainbowActive = false;
                break;
            case CMD_CALIBRATE:
                if (ImuManager::calibrate())
                    Serial.println("Calibration OK");
                else
                    Serial.println("Calibration FAIL — keep still");
                break;
        }
    }

    RoleCtrlCommand rcmd;
    if (EspNow::dequeueRoleCtrl(rcmd)) {
        g_txEnabled = (rcmd.txEnabled != 0);
        g_slaveMode = !g_txEnabled;
        saveRole(g_txEnabled);
        Serial.printf("Role: tx=%s\n", g_txEnabled ? "enabled" : "disabled");
    }

    // Dual-head slave: apply sync from master
    if (g_slaveMode) {
        SyncPacket spkt;
        if (EspNow::dequeueSyncPacket(spkt)) {
            lastSyncMs  = now;
            slaveSynced = true;
            switch (spkt.cmdType) {
                case CMD_LED_SOLID:
                    LedManager::solid(spkt.r, spkt.g, spkt.b, 200);  break;
                case CMD_LED_FLAME:
                    LedManager::flame();  break;
                case CMD_LED_RAINBOW:
                    LedManager::rainbow();  break;
                case CMD_LED_SPARKLE:
                    LedManager::sparkle(spkt.r, spkt.g, spkt.b, 128);  break;
                case CMD_LED_TILT:
                    LedManager::tiltFromHue(spkt.r);  break;
                default:
                    LedManager::off();  break;
            }
        } else if (slaveSynced && (now - lastSyncMs > 500)) {
            // Master lost — fall back to own IMU
            slaveSynced = false;
            LedManager::tilt(lastAngle);
        }
    }

    // Calibration command
    HubCommand calCmd;
    // handled inline: CMD_CALIBRATE is sent as a HubCommand with cmdType=CMD_CALIBRATE
    // (dequeueCommand already processes it above — handled in switch below)

    // Pairing ack → switch to unicast telemetry for real ACK-based heartbeat
    PairingAck ack;
    if (EspNow::dequeuePairingAck(ack)) {
        EspNow::setHubMac(ack.hubMac);
    }

#ifdef WIFI_SSID
    WifiCtrlCommand wcmd;
    if (EspNow::dequeueWifiCtrl(wcmd)) {
        if (wcmd.targetId == 0xFFFF || wcmd.targetId == EspNow::deviceId) {
            if (wcmd.state) wifiEnable();
            else            wifiDisable();
        }
    }
#endif
}

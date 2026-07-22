#include <Arduino.h>
#include <Preferences.h>
#include <math.h>
#include "Config.h"
#include "Protocol.h"
#include "EspNow.h"
#include "ImuManager.h"
#include "LedManager.h"
#ifdef WIFI_SSID
#include <WiFi.h>
#include <ArduinoOTA.h>
#include <esp_wifi.h>

#define WIFI_AUTO_OFF_MS (5UL * 60 * 1000)   // 5 min idle timeout — faster recovery if OTA
                                              // is never started; refreshed on every OTA
                                              // progress callback so an active transfer is
                                              // never cut off mid-flight (see wifiEnable()).

static bool     wifiActive       = false;
static uint32_t wifiEnabledAt    = 0;

static void wifiDisable() {
    if (!wifiActive) return;
    ArduinoOTA.end();
    WiFi.disconnect(true);
    // Joining the OTA AP locks the radio to its channel — restore the fixed
    // ESP-NOW channel or Hub/Slave communication stays broken until reboot.
    esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);
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
        // Keep pushing the idle timeout out while a transfer is actually running —
        // otherwise a slow build/upload step can race WIFI_AUTO_OFF_MS and the
        // device drops off WiFi mid-flash (esptool: "Host Not Found").
        ArduinoOTA.onStart([]() { wifiEnabledAt = millis(); });
        ArduinoOTA.onProgress([](unsigned int, unsigned int) { wifiEnabledAt = millis(); });
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
static bool     offActive        = false;  // explicit CMD_LED_OFF — distinct from "no override yet"
static float    lastAngle        = 0.0f;
static float    lastSpeed        = 0.0f;   // for IMU-reactive effect params (see resolveReactiveValue)
static uint8_t  lastFlags        = 0;      // STAFF_FLAG_* bitmask, ditto
static bool     sparkleActive    = false;
static uint8_t  sparkleR=255, sparkleG=255, sparkleB=255, sparkleDensity=128;
static uint8_t  solidR=0, solidG=0, solidB=0;  // last CMD_LED_SOLID color — forwarded to slave via sync
static bool     flameActive      = false;
static bool     rainbowActive    = false;
static bool     verticalActive   = false;
static bool     genericEffectActive = false;
static uint8_t  fxTemplate=0, fxPalette=0, fxSpeed=128, fxIntensity=200, fxParam1=0, fxParam2=0;
static uint8_t  fxReactiveSource=REACTIVE_NONE, fxReactiveParam=REACTIVE_PARAM_NONE;
static uint8_t  fxColorMode=COLOR_PALETTE, fxPr=0, fxPg=0, fxPb=0, fxSr=0, fxSg=0, fxSb=0;

// Resolves a curated IMU signal to a 0-255 byte for an IMU-reactive effect
// parameter. Uses the staff's OWN last-known telemetry (lastAngle/lastSpeed/
// lastFlags) — resolved locally on the Master, no extra radio traffic.
static uint8_t resolveReactiveValue(uint8_t source, float angle, float speed, uint8_t flags) {
    switch (source) {
        case REACTIVE_SPEED: {
            float v = speed / 15.0f;  // typical staff spin speed range ~0-15 rad/s
            if (v < 0.0f) v = 0.0f;
            if (v > 1.0f) v = 1.0f;
            return (uint8_t)(v * 255.0f);
        }
        case REACTIVE_ANGLE: {
            float t = (angle + 180.0f) / 360.0f;
            if (t < 0.0f) t = 0.0f;
            if (t > 1.0f) t = 1.0f;
            return (uint8_t)(t * 255.0f);
        }
        case REACTIVE_ORIENTATION: {
            uint8_t orient = flags & STAFF_FLAG_ORIENT_MASK;
            if (orient == STAFF_FLAG_ORIENT_VERT)  return 0;
            if (orient == STAFF_FLAG_ORIENT_HORIZ) return 128;
            return 255;  // inverted
        }
        case REACTIVE_SPIN:
            return (flags & STAFF_FLAG_SPIN_CW) ? 255 : 0;
        default:
            return 0;
    }
}

// Applies the active reactive binding (if any) on top of the static fx*
// values — called fresh each tick, both for the master's own render and
// for what gets mirrored to the slave, so the two always agree.
static void resolveEffectParams(uint8_t &outSpeed, uint8_t &outIntensity, uint8_t &outParam1) {
    outSpeed = fxSpeed; outIntensity = fxIntensity; outParam1 = fxParam1;
    if (fxReactiveSource == REACTIVE_NONE) return;
    uint8_t v = resolveReactiveValue(fxReactiveSource, lastAngle, lastSpeed, lastFlags);
    switch (fxReactiveParam) {
        case REACTIVE_PARAM_SPEED:     outSpeed = v;     break;
        case REACTIVE_PARAM_INTENSITY: outIntensity = v; break;
        case REACTIVE_PARAM_PARAM1:    outParam1 = v;    break;
    }
}
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
#ifdef WIFI_SSID
    // WiFi creds are compile-time constants (see wifiEnable()) — don't let the
    // driver persist/auto-reconnect to flash across reboots.
    WiFi.persistent(false);
#endif
    LedManager::init();
    imuOk = ImuManager::init();
    if (!imuOk) Serial.println("IMU init failed");
    uint8_t staffId = loadStaffId();
    EspNow::sendPairingRequest(staffId);
    EspNow::sendEffectList();   // advertise supported effects to Hub/Mac
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
            lastSpeed = imu.speed;
            lastFlags = imu.flags;
            SharedImuState imuState = {};
            ImuManager::readState(imuState);
            float currentHalfWindow = imuState.half_window;

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
                pkt.flags      = imu.flags;
                EspNow::sendTelemetry(pkt);

                // Broadcast direct PWM commands to stage lights if the Hub is offline (Autonomous Fallback)
                if (!EspNow::isHubAlive()) {
                    uint8_t w = 0, r = 0, g = 0, b = 0;
                    uint16_t fade = 100;
                    if (imu.flags & STAFF_FLAG_IMPACT) {
                        w = 255; r = 255; g = 255; b = 255;
                        fade = 0; // Strobe
                    } else if (imu.flags & STAFF_FLAG_THROW) {
                        w = 0; r = 0; g = 100; b = 255; // Cyan/blue float
                        fade = 50;
                    } else if (imu.flags & STAFF_FLAG_CATCH) {
                        w = 100; r = 255; g = 120; b = 0; // Orange catch burst
                        fade = 50;
                    } else {
                        if (imu.speed < 3.0f) {
                            w = 80; r = 30; g = 10; b = 0; // Default warm white
                            fade = 200;
                        } else {
                            fade = 80;
                            if (imu.angle > 0.0f) {
                                r = 255; g = 80; b = 0; // Flame/orange
                            } else {
                                g = 120; b = 255; // Electric cyan
                            }
                            float factor = min(1.0f, (imu.speed - 3.0f) / 10.0f);
                            r = (uint8_t)(r * factor);
                            g = (uint8_t)(g * factor);
                            b = (uint8_t)(b * factor);
                        }
                    }
                    EspNow::sendPWMCommand(0xFF, w, r, g, b, fade);
                }
            }

            // Master: send sync to slave every telemetry cycle.
            // Exactly ONE esp_now_send() call in this block, always — either the
            // legacy SyncPacket or the new EffectSyncPacket, never both. Extra
            // sends per tick previously congested the radio and dropped sync
            // packets to the slave (see 2026-07-19 root-cause-2 in DONE.md).
            if (g_txEnabled) {
                if (genericEffectActive) {
                    uint8_t rSpeed, rIntensity, rParam1;
                    resolveEffectParams(rSpeed, rIntensity, rParam1);
                    EspNow::sendEffectSyncPacket(fxTemplate, fxPalette, rSpeed,
                                                  rIntensity, rParam1, fxParam2,
                                                  fxColorMode, fxPr, fxPg, fxPb,
                                                  fxSr, fxSg, fxSb);
                } else {
                    uint8_t tiltHue     = (uint8_t)(((lastAngle + 90.0f) / 180.0f) * 170.0f);
                    bool    isVertical  = fabsf(lastAngle) <= currentHalfWindow;
                    uint8_t sc, sr, sg, sb;
                    if (offActive) {
                        sc = CMD_LED_OFF;
                        sr = 0;
                        sg = 0;
                        sb = 0;
                    } else if (cmdOverride && verticalActive) {
                        sc = CMD_LED_VERTICAL;
                        sr = isVertical ? 1 : 0;
                        sg = 0;
                        sb = 0;
                    } else if (cmdOverride) {
                        sc = flameActive ? CMD_LED_FLAME :
                             rainbowActive ? CMD_LED_RAINBOW :
                             sparkleActive ? CMD_LED_SPARKLE : CMD_LED_SOLID;
                        sr = sparkleActive ? sparkleR : solidR;
                        sg = sparkleActive ? sparkleG : solidG;
                        sb = sparkleActive ? sparkleB : solidB;
                    } else {
                        sc = CMD_LED_TILT;
                        sr = tiltHue;
                        sg = 0;
                        sb = 0;
                    }
                    EspNow::sendSyncPacket(sc, sr, sg, sb);
                }
            }
        }

        bool hubAlive = EspNow::isHubAlive();
        if (hubAlive && !g_hubWasAlive) {
            g_hubWasAlive = true;
            EspNow::sendAutonomous(1);  // Hub restored
            Serial.println("Hub restored — following commands");
        } else if (!hubAlive && g_hubWasAlive) {
            g_hubWasAlive = false;
            cmdOverride = false;
            offActive = false;  // OFF was a Hub instruction — don't hold it in autonomous mode
            EspNow::sendAutonomous(0);  // Hub lost → autonomous
            Serial.println("Hub lost — autonomous mode");
        }

        // Slave: LED state comes entirely from the master's SyncPacket
        // (handled below) — don't let our own IMU fight it for the display.
        if (!g_slaveMode) {
            SharedImuState imuState = {};
            ImuManager::readState(imuState);
            float currentHalfWindow = imuState.half_window;

            if (offActive && hubAlive) {
                LedManager::off();
            } else if (!cmdOverride || !hubAlive) {
                cmdOverride    = false;
                sparkleActive  = false;
                flameActive    = false;
                rainbowActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                LedManager::tilt(lastAngle);
            } else if (rainbowActive) {
                LedManager::rainbow();
            } else if (flameActive) {
                LedManager::flame();
            } else if (sparkleActive) {
                LedManager::sparkle(sparkleR, sparkleG, sparkleB, sparkleDensity);
            } else if (verticalActive) {
                LedManager::vertical(lastAngle, currentHalfWindow);
            } else if (genericEffectActive) {
                uint8_t rSpeed, rIntensity, rParam1;
                resolveEffectParams(rSpeed, rIntensity, rParam1);
                CRGBPalette16 pal = LedManager::resolvePalette(fxPalette, fxColorMode,
                                                                fxPr, fxPg, fxPb, fxSr, fxSg, fxSb);
                LedManager::genericEffect(fxTemplate, pal, rSpeed, rIntensity,
                                           rParam1, fxParam2, lastAngle, now);
            }
        }
    }

    HubCommand cmd;
    while (EspNow::dequeueCommand(cmd)) {
        switch (cmd.cmdType) {
            case CMD_LED_SOLID:
                LedManager::solid(cmd.r, cmd.g, cmd.b, cmd.brightness);
                solidR = cmd.r; solidG = cmd.g; solidB = cmd.b;
                cmdOverride    = true;
                offActive      = false;
                sparkleActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_LED_SPARKLE:
                sparkleR       = cmd.r;
                sparkleG       = cmd.g;
                sparkleB       = cmd.b;
                sparkleDensity = cmd.brightness;
                cmdOverride    = true;
                offActive      = false;
                sparkleActive  = true;
                flameActive    = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_LED_FLAME:
                cmdOverride    = true;
                offActive      = false;
                flameActive    = true;
                sparkleActive  = false;
                rainbowActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_LED_RAINBOW:
                cmdOverride    = true;
                offActive      = false;
                rainbowActive  = true;
                flameActive    = false;
                sparkleActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_LED_VERTICAL:
                cmdOverride    = true;
                offActive      = false;
                verticalActive = true;
                sparkleActive  = false;
                flameActive    = false;
                rainbowActive  = false;
                genericEffectActive = false;
                LedManager::vertical(lastAngle);
                break;
            case CMD_LED_OFF:
                LedManager::off();
                cmdOverride    = false;
                offActive      = true;
                sparkleActive  = false;
                flameActive    = false;
                rainbowActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_LED_TILT:
                // Explicit "back to default" — angle→hue, driven by the
                // staff's own IMU. Clears every override, including OFF.
                cmdOverride    = false;
                offActive      = false;
                sparkleActive  = false;
                flameActive    = false;
                rainbowActive  = false;
                verticalActive = false;
                genericEffectActive = false;
                break;
            case CMD_CALIBRATE:
                if (ImuManager::calibrate())
                    Serial.println("Calibration OK");
                else
                    Serial.println("Calibration FAIL — keep still");
                break;
        }
    }

    // Generic parametrized FastLED effect — separate queue/struct from the
    // 6 fixed CmdType effects above (see EffectCommand in Protocol.h).
    EffectCommand fxCmd;
    while (EspNow::dequeueEffectCommand(fxCmd)) {
        fxTemplate     = fxCmd.templateId;
        fxPalette      = fxCmd.paletteId;
        fxSpeed        = fxCmd.speed;
        fxIntensity    = fxCmd.intensity;
        fxParam1       = fxCmd.param1;
        fxParam2       = fxCmd.param2;
        fxReactiveSource = fxCmd.reactiveSource;
        fxReactiveParam  = fxCmd.reactiveParam;
        fxColorMode    = fxCmd.colorMode;
        fxPr = fxCmd.pr; fxPg = fxCmd.pg; fxPb = fxCmd.pb;
        fxSr = fxCmd.sr; fxSg = fxCmd.sg; fxSb = fxCmd.sb;
        cmdOverride    = true;
        offActive      = false;
        sparkleActive  = false;
        flameActive    = false;
        rainbowActive  = false;
        verticalActive = false;
        genericEffectActive = true;
    }

    RoleCtrlCommand rcmd;
    if (EspNow::dequeueRoleCtrl(rcmd)) {
        g_txEnabled = (rcmd.txEnabled != 0);
        g_slaveMode = !g_txEnabled;
        saveRole(g_txEnabled);
        Serial.printf("Role: tx=%s\n", g_txEnabled ? "enabled" : "disabled");
    }

    // Dual-head slave: apply sync from master. Master sends exactly ONE of
    // SyncPacket / EffectSyncPacket per cycle (never both) — check both queues.
    if (g_slaveMode) {
        bool synced = false;
        SyncPacket spkt;
        EffectSyncPacket fxSpkt;
        if (EspNow::dequeueSyncPacket(spkt)) {
            synced = true;
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
                case CMD_LED_VERTICAL:
                    LedManager::verticalFromFlag(spkt.r);  break;
                default:
                    LedManager::off();  break;
            }
        } else if (EspNow::dequeueEffectSyncPacket(fxSpkt)) {
            synced = true;
            CRGBPalette16 pal = LedManager::resolvePalette(fxSpkt.paletteId, fxSpkt.colorMode,
                                                            fxSpkt.pr, fxSpkt.pg, fxSpkt.pb,
                                                            fxSpkt.sr, fxSpkt.sg, fxSpkt.sb);
            LedManager::genericEffect(fxSpkt.templateId, pal, fxSpkt.speed,
                                       fxSpkt.intensity, fxSpkt.param1, fxSpkt.param2, lastAngle, now);
        }

        if (synced) {
            lastSyncMs  = now;
            slaveSynced = true;
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

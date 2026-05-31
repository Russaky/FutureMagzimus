#include <Arduino.h>
#include "Config.h"
#include "Protocol.h"
#include "SerialBridge.h"
#include "EspNow.h"

static uint32_t pauseUntilMs = 0;

static void onSerialCommand(uint8_t msgType, const uint8_t *payload, uint16_t len) {
    switch (msgType) {
        case MSG_CMD_STAFF:
            if (len == sizeof(HubCommand))    EspNow::send(payload, len); break;
        case MSG_CMD_RELAY:
            if (len == sizeof(RelayCommand))  EspNow::send(payload, len); break;
        case MSG_CMD_PWM:
            if (len == sizeof(PWMCommand))    EspNow::send(payload, len); break;
        case MSG_DISCOVER:
            EspNow::sendDiscover(); break;
        case MSG_WIFI_CTRL:
            if (len == sizeof(WifiCtrlCommand)) EspNow::send(payload, len); break;
        case MSG_ROLE_CTRL:
            if (len == sizeof(RoleCtrlCommand)) EspNow::send(payload, len); break;
        case MSG_PAIR_ACK:
            if (len == sizeof(PairingAck))      EspNow::send(payload, len); break;
        case MSG_CALIBRATE:
            if (len == sizeof(HubCommand))      EspNow::send(payload, len); break;
        case MSG_HUB_PAUSE:
            if (len >= 1) pauseUntilMs = millis() + (uint32_t)payload[0] * 1000; break;
    }
}

void setup() {
    SerialBridge::begin(SERIAL_BAUD, onSerialCommand);
    EspNow::init();
    Serial.printf("Hub ready  FW:%s\n", FIRMWARE_VERSION);
}

static uint32_t lastAliveMs = 0;

void loop() {
    SerialBridge::poll();
    uint32_t now = millis();
    if (now - lastAliveMs >= 1000 && now > pauseUntilMs) {
        lastAliveMs = now;
        EspNow::sendAlive();
    }
}

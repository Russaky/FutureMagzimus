/*
 * DMX512 Controller — ESP32-S3 SuperMini + MAX485
 * ================================================
 * Receives DMXCommand over ESP-NOW from the Hub and forwards it to a
 * continuous DMX512 transmission at ~40Hz. Library: esp_dmx by someweisguy.
 */

#include <Arduino.h>
#include <esp_dmx.h>
#include "Config.h"
#include "Protocol.h"
#include "EspNow.h"

// Full buffer of 513 bytes (byte 0 = start code, channels 1-512)
static uint8_t dmxData[DMX_PACKET_SIZE] = {0};

static uint32_t lastFrameTime = 0;

void setup() {
    Serial.begin(115200);

    dmx_config_t config = DMX_CONFIG_DEFAULT;
    if (!dmx_driver_install(DMX_PORT_NUM, &config, NULL, 0)) {
        Serial.println("Failed to install DMX driver! Halting...");
        while (1) { delay(100); }
    }
    dmx_set_pin(DMX_PORT_NUM, DMX_TX_PIN, DMX_RX_PIN, DMX_PIN_NO_CHANGE);

    // EN constant HIGH — MAX485 always in Driver Enable (transmit)
    pinMode(DMX_ENABLE_PIN, OUTPUT);
    digitalWrite(DMX_ENABLE_PIN, HIGH);

    EspNow::init();
    Serial.printf("DMX Controller ready  ID:%04X  FW:%s\n", EspNow::deviceId, FIRMWARE_VERSION);
}

void loop() {
    EspNow::pollDiscover();

    DMXCommand cmd;
    while (EspNow::dequeue(cmd)) {
        uint16_t addr = cmd.targetAddr;
        Serial.printf("DMXCommand recv: addr=%u w=%u r=%u g=%u b=%u\n",
                      addr, cmd.w, cmd.r, cmd.g, cmd.b);
        if (addr >= 1 && addr + 3 <= 512) {
            dmxData[addr]     = cmd.w;
            dmxData[addr + 1] = cmd.r;
            dmxData[addr + 2] = cmd.g;
            dmxData[addr + 3] = cmd.b;
        }
    }

    uint32_t now = millis();
    if (now - lastFrameTime >= FRAME_INTERVAL_MS) {
        lastFrameTime = now;
        dmx_write(DMX_PORT_NUM, dmxData, DMX_PACKET_SIZE);
        dmx_send(DMX_PORT_NUM);
        dmx_wait_sent(DMX_PORT_NUM, DMX_TIMEOUT_TICK);
    }
}

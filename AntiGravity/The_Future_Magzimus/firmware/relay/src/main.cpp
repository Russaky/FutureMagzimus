#include <Arduino.h>
#include "Config.h"
#include "Protocol.h"
#include "EspNow.h"

static uint32_t shutoffAt = 0;

void setup() {
    Serial.begin(115200);
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, LOW);
    EspNow::init();
    Serial.printf("Relay ready  ID:%02X  FW:%s\n", EspNow::deviceId, FIRMWARE_VERSION);
}

void loop() {
    RelayCommand cmd;
    while (EspNow::dequeue(cmd)) {
        if (cmd.state == 1) {
            digitalWrite(RELAY_PIN, HIGH);
            shutoffAt = (cmd.durationMs > 0) ? millis() + cmd.durationMs : 0;
        } else {
            digitalWrite(RELAY_PIN, LOW);
            shutoffAt = 0;
        }
    }

    // Safety auto-shutoff
    if (shutoffAt > 0 && millis() >= shutoffAt) {
        digitalWrite(RELAY_PIN, LOW);
        shutoffAt = 0;
    }
}

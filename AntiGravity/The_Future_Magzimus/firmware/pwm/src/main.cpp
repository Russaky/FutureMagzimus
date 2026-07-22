#include <Arduino.h>
#include "Config.h"

#ifdef GPIO_SCAN

static const uint8_t SCAN_PINS[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20, 21};
static const uint8_t N_PINS = sizeof(SCAN_PINS);

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("[GPIO SCAN] Starting — 1 sec per pin, HIGH then LOW");
    for (uint8_t i = 0; i < N_PINS; i++) {
        pinMode(SCAN_PINS[i], OUTPUT);
        digitalWrite(SCAN_PINS[i], LOW);
    }
}

void loop() {
    for (uint8_t i = 0; i < N_PINS; i++) {
        Serial.printf("[GPIO SCAN] GPIO %d HIGH\n", SCAN_PINS[i]);
        digitalWrite(SCAN_PINS[i], HIGH);
        delay(1000);
        digitalWrite(SCAN_PINS[i], LOW);
    }
    Serial.println("[GPIO SCAN] cycle done, repeating...");
    delay(500);
}

#else

#include "Protocol.h"
#include "EspNow.h"

static void applyPWM(uint8_t w, uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(0, w);
    ledcWrite(1, r);
    ledcWrite(2, g);
    ledcWrite(3, b);
}

// Last applied state — kept in RAM only, starts at all-off (per spec)
static uint8_t curW = 0, curR = 0, curG = 0, curB = 0;

void setup() {
    Serial.begin(115200);

    // Pull WRGB pins low immediately, before LEDC/WiFi init
    pinMode(PWM_PIN_W, OUTPUT); digitalWrite(PWM_PIN_W, LOW);
    pinMode(PWM_PIN_R, OUTPUT); digitalWrite(PWM_PIN_R, LOW);
    pinMode(PWM_PIN_G, OUTPUT); digitalWrite(PWM_PIN_G, LOW);
    pinMode(PWM_PIN_B, OUTPUT); digitalWrite(PWM_PIN_B, LOW);

    ledcSetup(0, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_W, 0);
    ledcSetup(1, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_R, 1);
    ledcSetup(2, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_G, 2);
    ledcSetup(3, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_B, 3);
    applyPWM(0, 0, 0, 0);
    EspNow::init();
    Serial.printf("Node ready  ID:%d  FW:%s\n", EspNow::deviceId, FIRMWARE_VERSION);
}

static String s_serialBuf;

static void pollSerial() {
    while (Serial.available()) {
        char c = Serial.read();
        if (c == '\n') {
            // format: W,R,G,B
            int v[4] = {0,0,0,0};
            int idx = 0;
            char *tok = strtok(&s_serialBuf[0], ",");
            while (tok && idx < 4) { v[idx++] = atoi(tok); tok = strtok(nullptr, ","); }
            curW = v[0]; curR = v[1]; curG = v[2]; curB = v[3];
            applyPWM(curW, curR, curG, curB);
            Serial.printf("PWM W:%d R:%d G:%d B:%d\n", curW, curR, curG, curB);
            s_serialBuf = "";
        } else if (c != '\r') {
            s_serialBuf += c;
        }
    }
}

void loop() {
    light_cmd_t cmd;
    while (EspNow::dequeue(cmd)) {
        if (cmd.w == curW && cmd.r == curR && cmd.g == curG && cmd.b == curB) continue;
        curW = cmd.w; curR = cmd.r; curG = cmd.g; curB = cmd.b;
        applyPWM(curW, curR, curG, curB);
        EspNow::sendAck(curW, curR, curG, curB);
    }
    pollSerial();
}

#endif // GPIO_SCAN

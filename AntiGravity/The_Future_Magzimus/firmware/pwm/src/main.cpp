#include <Arduino.h>
#include "Config.h"
#include "Protocol.h"
#include "EspNow.h"

static uint8_t lerp8(uint8_t a, uint8_t b, float t) {
    return (uint8_t)((int)a + (int)((int)b - (int)a) * t);
}

static void applyPWM(uint8_t w, uint8_t r, uint8_t g, uint8_t b) {
    ledcWrite(0, w);
    ledcWrite(1, r);
    ledcWrite(2, g);
    ledcWrite(3, b);
}

// Fade state
static uint8_t  fromW = 0, fromR = 0, fromG = 0, fromB = 0;
static uint8_t  toW   = 0, toR   = 0, toG   = 0, toB   = 0;
static uint8_t  curW  = 0, curR  = 0, curG  = 0, curB  = 0;
static uint32_t fadeStart    = 0;
static uint16_t fadeDuration = 0;

void setup() {
    Serial.begin(115200);
    ledcSetup(0, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_W, 0);
    ledcSetup(1, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_R, 1);
    ledcSetup(2, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_G, 2);
    ledcSetup(3, PWM_FREQ, PWM_BITS); ledcAttachPin(PWM_PIN_B, 3);
    applyPWM(0, 0, 0, 0);
    EspNow::init();
    Serial.printf("PWM ready  ID:%02X  FW:%s\n", EspNow::deviceId, FIRMWARE_VERSION);
}

void loop() {
    PWMCommand cmd;
    while (EspNow::dequeue(cmd)) {
        // Capture current value (handles mid-fade interruption)
        if (fadeDuration > 0) {
            float t = min(1.0f, (float)(millis() - fadeStart) / fadeDuration);
            curW = lerp8(fromW, toW, t);
            curR = lerp8(fromR, toR, t);
            curG = lerp8(fromG, toG, t);
            curB = lerp8(fromB, toB, t);
        }

        if (cmd.fadeMs == 0) {
            curW = cmd.w; curR = cmd.r; curG = cmd.g; curB = cmd.b;
            fadeDuration = 0;
            applyPWM(curW, curR, curG, curB);
        } else {
            fromW = curW; fromR = curR; fromG = curG; fromB = curB;
            toW = cmd.w;  toR = cmd.r;  toG = cmd.g;  toB = cmd.b;
            fadeStart    = millis();
            fadeDuration = cmd.fadeMs;
        }
    }

    // Fade interpolation
    if (fadeDuration > 0) {
        uint32_t elapsed = millis() - fadeStart;
        if (elapsed >= fadeDuration) {
            curW = toW; curR = toR; curG = toG; curB = toB;
            fadeDuration = 0;
            applyPWM(curW, curR, curG, curB);
        } else {
            float t = (float)elapsed / fadeDuration;
            applyPWM(lerp8(fromW, toW, t), lerp8(fromR, toR, t),
                     lerp8(fromG, toG, t), lerp8(fromB, toB, t));
        }
    }
}

#include "LedManager.h"
#include "Config.h"
#include <FastLED.h>

static CRGB leds[NUM_LEDS_PHYSICAL];

// Copy leds[0..NUM_LEDS-1] to all 5 physical strips (zigzag layout).
static void applyZigzag() {
    for (int s = 0; s < 5; s++) {
        for (int i = 0; i < NUM_LEDS; i++) {
            int dst = s * NUM_LEDS + i;
            leds[dst] = (s % 2 == 0) ? leds[i] : leds[NUM_LEDS - 1 - i];
        }
    }
}


void LedManager::init() {
    FastLED.addLeds<WS2812B, LED_PIN, GRB>(leds, NUM_LEDS_PHYSICAL);
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    off();
}

void LedManager::solid(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness) {
    fill_solid(leds, NUM_LEDS, CRGB(r, g, b));
    applyZigzag();
    uint8_t clamped = brightness > LED_MAX_BRIGHTNESS ? LED_MAX_BRIGHTNESS : brightness;
    FastLED.setBrightness(clamped);
    FastLED.show();
}


void LedManager::sparkle(uint8_t r, uint8_t g, uint8_t b, uint8_t density) {
    for (int i = 0; i < NUM_LEDS; i++) {
        if (random8() < density)
            leds[i] = CRGB(r, g, b);
        else
            leds[i] = leds[i].nscale8(180);  // fade non-lit LEDs
    }
    applyZigzag();
    FastLED.show();
}

void LedManager::flame() {
    for (int i = 0; i < NUM_LEDS; i++) {
        uint8_t hue     = random8(0, 28);      // red → orange → yellow tip
        uint8_t bright  = random8(120, 255);   // flicker
        uint8_t sat     = random8(210, 255);   // mostly saturated, occasional white tip
        leds[i] = CHSV(hue, sat, bright);
    }
    applyZigzag();
    FastLED.show();
}

void LedManager::rainbow() {
    static uint8_t hue = 0;
    for (int i = 0; i < NUM_LEDS; i++)
        leds[i] = CHSV(hue + (uint8_t)(i * 256 / NUM_LEDS), 255, 200);
    applyZigzag();
    FastLED.show();
    hue += 3;
}

void LedManager::tiltFromHue(uint8_t hue) {
    fill_solid(leds, NUM_LEDS, CHSV(hue, 255, 200));
    applyZigzag();
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    FastLED.show();
}

// Virtual pixel → physical LED index.
// Section A: virtual 0..(NUM_LEDS_SECTION-1) → physical 0..49 (forward)
// Gap:        virtual NUM_LEDS_SECTION..(NUM_LEDS_SECTION+GAP_VIRTUAL-1) → -1
// Section B:  virtual (NUM_LEDS_SECTION+GAP_VIRTUAL)..NUM_LEDS_VIRTUAL-1 → physical 99..50 (serpentine reverse)
int LedManager::XY(int v) {
    if (v < 0 || v >= NUM_LEDS_VIRTUAL) return -1;
    if (v < NUM_LEDS_SECTION) return v;
    if (v < NUM_LEDS_SECTION + GAP_VIRTUAL) return -1;
    return NUM_LEDS_PHYSICAL - 1 - (v - NUM_LEDS_SECTION - GAP_VIRTUAL);
}

void LedManager::tilt(float angleDeg) {
    // Map -90°..+90° → hue 0 (red) → 85 (green) → 170 (blue)
    float t   = (angleDeg + 90.0f) / 180.0f;
    if (t < 0.0f) t = 0.0f;
    if (t > 1.0f) t = 1.0f;
    uint8_t hue = (uint8_t)(t * 170.0f);
    fill_solid(leds, NUM_LEDS, CHSV(hue, 255, 200));
    applyZigzag();
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    FastLED.show();
}

void LedManager::off() {
    fill_solid(leds, NUM_LEDS_PHYSICAL, CRGB::Black);
    FastLED.show();
}

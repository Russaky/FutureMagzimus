#include "LedManager.h"
#include "Config.h"
#include "EffectPresets.h"
#include "Protocol.h"   // EffectTemplate / EffectPalette / NUM_EFFECT_* constants
#include <FastLED.h>
#include <math.h>

static CRGB leds[NUM_LEDS_PHYSICAL];

// Built-in FastLED gradient palettes, indexed by EffectPalette (Protocol.h).
static const CRGBPalette16 kEffectPalettes[NUM_EFFECT_PALETTES] = {
    RainbowColors_p, HeatColors_p, LavaColors_p, OceanColors_p, ForestColors_p, PartyColors_p
};

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
    FastLED.setMaxPowerInVoltsAndMilliamps(5, 1000);
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
            leds[i] = leds[i].nscale8(PRESET_SPARKLE_FADE);
    }
    applyZigzag();
    FastLED.show();
}

void LedManager::flame() {
    for (int i = 0; i < NUM_LEDS; i++) {
        uint8_t hue    = random8(0, PRESET_FLAME_HUE_MAX);
        uint8_t bright = random8(PRESET_FLAME_BRIGHT_MIN, 255);
        uint8_t sat    = random8(PRESET_FLAME_SAT_MIN, 255);
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
    hue += PRESET_RAINBOW_STEP;
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

// CMD_LED_VERTICAL preset: green while the head points straight up
// (|angle| within LED_VERTICAL_GREEN_WINDOW_DEG of 0°), blue otherwise.
// `angle` is pitch in -180..180 with 0°=vertical-up — only the up pass
// counts as "vertical" here (±180° = pointing down / inverted is excluded).
void LedManager::vertical(float angleDeg, float halfWindow) {
    verticalFromFlag(fabsf(angleDeg) <= halfWindow ? 1 : 0);
}

void LedManager::verticalFromFlag(uint8_t isVertical) {
    CRGB color = isVertical ? CRGB(0, 255, 0) : CRGB(0, 0, 255);
    fill_solid(leds, NUM_LEDS, color);
    applyZigzag();
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    FastLED.show();
}

void LedManager::hueToRgb(uint8_t hue, uint8_t &r, uint8_t &g, uint8_t &b) {
    CRGB c = CHSV(hue, 255, 200);
    r = c.r; g = c.g; b = c.b;
}

void LedManager::off() {
    fill_solid(leds, NUM_LEDS_PHYSICAL, CRGB::Black);
    FastLED.show();
}

CRGBPalette16 LedManager::resolvePalette(uint8_t paletteId, uint8_t colorMode,
                                          uint8_t pr, uint8_t pg, uint8_t pb,
                                          uint8_t sr, uint8_t sg, uint8_t sb) {
    if (colorMode == COLOR_CUSTOM)
        return CRGBPalette16(CRGB(pr, pg, pb), CRGB(sr, sg, sb));
    return kEffectPalettes[paletteId % NUM_EFFECT_PALETTES];
}

void LedManager::genericEffect(uint8_t templateId, const CRGBPalette16 &pal, uint8_t speed,
                                uint8_t intensity, uint8_t param1, uint8_t param2,
                                float currentAngle, uint32_t nowMs) {
    switch (templateId % NUM_EFFECT_TEMPLATES) {
        case FX_SOLID: {
            CRGB color = ColorFromPalette(pal, 0, intensity);
            fill_solid(leds, NUM_LEDS, color);
            break;
        }
        case FX_GRADIENT: {
            // speed 0-255 → shift 0..~8 per ms; higher speed scrolls faster.
            // param1 selects scroll direction: <128 forward, >=128 reverse.
            bool reverse = param1 >= 128;
            uint8_t shift = (uint8_t)((nowMs * (1 + speed / 16)) / 8);
            if (reverse) shift = (uint8_t)(0 - shift);
            for (int i = 0; i < NUM_LEDS; i++)
                leds[i] = ColorFromPalette(pal, shift + (uint8_t)(i * 255 / NUM_LEDS), intensity);
            break;
        }
        case FX_WAVE: {
            uint8_t trailWidth = 6 + param1 / 3;   // param1 → trail/width
            fadeToBlackBy(leds, NUM_LEDS, trailWidth);
            // beatsin16 reads the live clock internally — no need to pass nowMs.
            int pos = beatsin16(1 + speed / 8, 0, NUM_LEDS - 1);
            leds[pos] += ColorFromPalette(pal, (uint8_t)(nowMs / 8), intensity);
            break;
        }
        case FX_FADE: {
            uint8_t bpm     = 10 + speed / 2;
            uint8_t minBri  = param1;                       // min brightness floor
            uint8_t maxBri  = param2 > minBri ? param2 : 255; // max brightness ceiling
            uint8_t beat    = beatsin8(bpm, minBri, maxBri); // beatsin8 reads the live clock internally
            for (int i = 0; i < NUM_LEDS; i++)
                leds[i] = ColorFromPalette(pal, (uint8_t)(nowMs / 16 + i * 2),
                                            scale8(beat, intensity));
            break;
        }
        case FX_SPARKLE: {
            uint8_t decay = 4 + param1 / 3;   // param1 → fade-tail decay
            fadeToBlackBy(leds, NUM_LEDS, decay);
            if (random8() < (1 + speed / 4)) {  // speed doubles as spawn density
                int pos = random16(NUM_LEDS);
                leds[pos] = ColorFromPalette(pal, random8(), intensity);
            }
            break;
        }
        case FX_THEATER_CHASE: {
            uint32_t period = 40 + (uint32_t)(255 - speed);   // ms per chase step
            uint8_t step = (uint8_t)((nowMs / period) % 3);
            for (int i = 0; i < NUM_LEDS; i++)
                leds[i] = ((i + step) % 3 == 0)
                              ? ColorFromPalette(pal, (uint8_t)(i * 255 / NUM_LEDS), intensity)
                              : CRGB::Black;
            break;
        }
        case FX_FLAME: {
            // Fire2012-style simulation (Malcolm/FastLED classic). speed → cooling
            // (higher = flames die out faster), param1 → sparking (higher = more
            // frequent new sparks). Renders through `pal` like everything else —
            // built-in Heat/Lava palette, or a custom primary/secondary gradient.
            static uint8_t heat[NUM_LEDS] = {0};
            uint8_t cooling  = 20 + speed / 4;
            uint8_t sparking = 50 + param1 / 2;
            for (int i = 0; i < NUM_LEDS; i++) {
                uint8_t cooldown = random8(0, ((cooling * 10) / NUM_LEDS) + 2);
                heat[i] = (cooldown >= heat[i]) ? 0 : heat[i] - cooldown;
            }
            for (int i = NUM_LEDS - 1; i >= 2; i--)
                heat[i] = (heat[i - 1] + heat[i - 2] + heat[i - 2]) / 3;
            if (random8() < sparking) {
                int y = random8(7);
                heat[y] = qadd8(heat[y], random8(160, 255));
            }
            for (int i = 0; i < NUM_LEDS; i++)
                leds[i] = ColorFromPalette(pal, scale8(heat[i], 240), intensity);
            break;
        }
        case FX_VERTICAL: {
            // Status-indicator effect (was Legacy Vertical) — fixed green/blue,
            // not a color effect, so colorMode/pal are intentionally ignored.
            // param1 = angle window in degrees (0 = fall back to the old default ~15°).
            float halfWindow = param1 > 0 ? (float)param1 : 15.0f;
            bool  isVertical = fabsf(currentAngle) <= halfWindow;
            fill_solid(leds, NUM_LEDS, isVertical ? CRGB(0, 255, 0) : CRGB(0, 0, 255));
            break;
        }
    }
    applyZigzag();
    FastLED.setBrightness(LED_MAX_BRIGHTNESS);
    FastLED.show();
}

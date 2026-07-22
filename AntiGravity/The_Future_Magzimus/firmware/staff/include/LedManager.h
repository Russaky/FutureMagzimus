#pragma once
#include <stdint.h>
#include <FastLED.h>
#include "Config.h"

class LedManager {
public:
    static void init();
    static void solid(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness);
    static void sparkle(uint8_t r, uint8_t g, uint8_t b, uint8_t density);
    static void flame();
    static void rainbow();
    static void tilt(float angleDeg);
    static void tiltFromHue(uint8_t hue);
    static void vertical(float angleDeg, float halfWindow = LED_VERTICAL_GREEN_WINDOW_DEG);
    static void verticalFromFlag(uint8_t isVertical);
    static void off();

    // Builds the CRGBPalette16 a generic effect should render through: either
    // one of the NUM_EFFECT_PALETTES built-ins (colorMode == COLOR_PALETTE),
    // or a 2-stop gradient built from primary->secondary on the fly
    // (colorMode == COLOR_CUSTOM). Every template already renders via
    // ColorFromPalette(), so this is the only place custom color needs to
    // be resolved — no per-template special-casing.
    static CRGBPalette16 resolvePalette(uint8_t paletteId, uint8_t colorMode,
                                         uint8_t pr, uint8_t pg, uint8_t pb,
                                         uint8_t sr, uint8_t sg, uint8_t sb);

    // Generic FastLED-based parametrized effect (see EffectTemplate in
    // Protocol.h). One rendering function shared by every template — new
    // "effects" are just new (templateId, pal, speed, intensity, param1,
    // param2) presets, no new firmware function required. `currentAngle`
    // is only used by FX_VERTICAL (pitch in degrees, 0 = vertical-up).
    static void genericEffect(uint8_t templateId, const CRGBPalette16 &pal, uint8_t speed,
                               uint8_t intensity, uint8_t param1, uint8_t param2,
                               float currentAngle, uint32_t nowMs);

    // Same HSV curve used by tilt()/tiltFromHue() — for mirroring the active
    // color to other outputs (e.g. DMX) without touching the LED strip.
    static void hueToRgb(uint8_t hue, uint8_t &r, uint8_t &g, uint8_t &b);

    // Virtual pixel API — serpentine layout with gap
    // Returns physical LED index for virtual position, or -1 if in gap
    static int  XY(int virtualIdx);
};

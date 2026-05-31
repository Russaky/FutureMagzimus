#pragma once
#include <stdint.h>

class LedManager {
public:
    static void init();
    static void solid(uint8_t r, uint8_t g, uint8_t b, uint8_t brightness);
    static void sparkle(uint8_t r, uint8_t g, uint8_t b, uint8_t density);
    static void flame();
    static void rainbow();
    static void tilt(float angleDeg);
    static void tiltFromHue(uint8_t hue);
    static void off();

    // Virtual pixel API — serpentine layout with gap
    // Returns physical LED index for virtual position, or -1 if in gap
    static int  XY(int virtualIdx);
};

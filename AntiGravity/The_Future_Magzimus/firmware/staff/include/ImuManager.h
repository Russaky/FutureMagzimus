#pragma once
#include <stdint.h>

struct ImuData {
    int16_t accX, accY, accZ;
    int16_t gyroX, gyroY, gyroZ;
    float   speed;   // rotation magnitude (rad/s)
    float   angle;   // pitch (degrees)
};

class ImuManager {
public:
    static bool init();
    static bool read(ImuData &out);
    // Sample 200 readings at rest → store gyro/accel offsets in RAM.
    // Returns false if device is moving (speed > 0.3 rad/s) or read fails.
    static bool calibrate();
    static bool isCalibrated();
};

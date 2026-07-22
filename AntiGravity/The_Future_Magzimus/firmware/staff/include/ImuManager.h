#pragma once
#include <stdint.h>

struct ImuData {
    int16_t accX, accY, accZ;
    int16_t gyroX, gyroY, gyroZ;
    float   speed;   // rotation magnitude (rad/s)
    float   angle;   // pitch (degrees)
    uint8_t flags;   // STAFF_FLAG_* bitmask — computed each cycle
};

struct SharedImuState {
    float pitch;
    float roll;
    float spin_speed;
    bool  in_free_fall;
    bool  gyro_saturated;
    bool  accel_clipped;
    int16_t accX, accY, accZ;
    int16_t gyroX, gyroY, gyroZ;
    uint8_t flags;
    float   half_window;
};

class ImuManager {
public:
    static bool init();
    static bool read(ImuData &out);
    static bool readState(SharedImuState &out);
    // Sample 200 readings at rest → store gyro/accel offsets in RAM.
    // Returns false if device is moving (speed > 0.3 rad/s) or read fails.
    static bool calibrate();
    static bool isCalibrated();
    static void update();
};

#pragma once
#include <math.h>

class MadgwickFilter {
private:
    float beta;
    float q0, q1, q2, q3; // quaternion
    float sampleFreq;

public:
    MadgwickFilter();
    void begin(float freq);
    void setBeta(float b);
    void updateIMU(float gx, float gy, float gz, float ax, float ay, float az);
    float getPitch();
    float getRoll();
};

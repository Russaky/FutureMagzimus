#include "ImuManager.h"
#include "Config.h"
#include <Arduino.h>
#include <Wire.h>
#include <math.h>

static int16_t s_offGx=0, s_offGy=0, s_offGz=0;
static int16_t s_offAx=0, s_offAy=0;
static bool    s_calibrated = false;

static bool readRaw(int16_t &ax, int16_t &ay, int16_t &az,
                    int16_t &gx, int16_t &gy, int16_t &gz) {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x3B);
    if (Wire.endTransmission(false) != 0) return false;
    Wire.requestFrom(IMU_ADDR, (uint8_t)14);
    if (Wire.available() < 14) return false;
    ax=(Wire.read()<<8)|Wire.read(); ay=(Wire.read()<<8)|Wire.read();
    az=(Wire.read()<<8)|Wire.read();
    Wire.read(); Wire.read();
    gx=(Wire.read()<<8)|Wire.read(); gy=(Wire.read()<<8)|Wire.read();
    gz=(Wire.read()<<8)|Wire.read();
    return true;
}

static void writeReg(uint8_t reg, uint8_t val) {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(reg);
    Wire.write(val);
    Wire.endTransmission();
}

bool ImuManager::init() {
    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);
    delay(50);
    writeReg(0x6B, 0x00); // wake up
    delay(10);
    writeReg(0x1B, 0x00); // gyro  ±250 °/s
    writeReg(0x1C, 0x00); // accel ±2 g

    uint8_t addrs[2] = {0x68, 0x69};
    for (int i = 0; i < 2; i++) {
        uint8_t addr = addrs[i];
        Wire.beginTransmission(addr);
        Wire.write(0x75); // WHO_AM_I
        Wire.endTransmission(false);
        Wire.requestFrom((uint8_t)addr, (uint8_t)1);
        uint8_t who = (Wire.available() > 0) ? Wire.read() : 0xFF;
        Serial.printf("I2C addr=0x%02X  WHO_AM_I=0x%02X\n", addr, who);
        if (who == 0x68 || who == 0x70) return true;  // 0x68=MPU6050, 0x70=MPU6500
    }
    return false;
}

bool ImuManager::isCalibrated() { return s_calibrated; }

bool ImuManager::calibrate() {
    int16_t ax, ay, az, gx, gy, gz;
    // Static detection: 10 samples must show near-zero rotation
    for (int i = 0; i < 10; i++) {
        if (!readRaw(ax, ay, az, gx, gy, gz)) return false;
        float spd = sqrtf((gx/131.0f)*(gx/131.0f) +
                          (gy/131.0f)*(gy/131.0f) +
                          (gz/131.0f)*(gz/131.0f)) * (float)M_PI / 180.0f;
        if (spd > 0.3f) return false;
        delay(20);
    }
    // 200 samples over ~500ms
    int32_t sGx=0, sGy=0, sGz=0, sAx=0, sAy=0;
    for (int i = 0; i < 200; i++) {
        if (!readRaw(ax, ay, az, gx, gy, gz)) return false;
        sGx+=gx; sGy+=gy; sGz+=gz; sAx+=ax; sAy+=ay;
        delay(2);
    }
    s_offGx=sGx/200; s_offGy=sGy/200; s_offGz=sGz/200;
    s_offAx=sAx/200; s_offAy=sAy/200;
    s_calibrated = true;
    Serial.printf("Cal: offG=(%d,%d,%d) offA=(%d,%d)\n",
                  s_offGx, s_offGy, s_offGz, s_offAx, s_offAy);
    return true;
}

bool ImuManager::read(ImuData &out) {
    int16_t ax, ay, az, gx, gy, gz;
    if (!readRaw(ax, ay, az, gx, gy, gz)) return false;
    out.accX  = ax - s_offAx;
    out.accY  = ay - s_offAy;
    out.accZ  = az;
    out.gyroX = gx - s_offGx;
    out.gyroY = gy - s_offGy;
    out.gyroZ = gz - s_offGz;

    // gyro: 131 LSB/(°/s) at ±250°/s → convert to rad/s
    float fgx = out.gyroX / 131.0f * (float)M_PI / 180.0f;
    float fgy = out.gyroY / 131.0f * (float)M_PI / 180.0f;
    float fgz = out.gyroZ / 131.0f * (float)M_PI / 180.0f;
    out.speed = sqrtf(fgx*fgx + fgy*fgy + fgz*fgz);

    // pitch from accel (degrees)
    out.angle = atan2f((float)out.accX,
                       sqrtf((float)out.accY * out.accY +
                             (float)out.accZ * out.accZ)) * 180.0f / (float)M_PI;

    return true;
}

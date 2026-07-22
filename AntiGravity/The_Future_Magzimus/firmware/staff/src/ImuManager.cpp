#include "ImuManager.h"
#include "MadgwickFilter.h"
#include "Protocol.h"
#include "Config.h"
#include <Arduino.h>
#include <Wire.h>
#include <math.h>

static float s_offGx_f = 0.0f, s_offGy_f = 0.0f, s_offGz_f = 0.0f;
static float s_offAx_f = 0.0f, s_offAy_f = 0.0f;
static bool  s_calibrated = false;

static SharedImuState s_sharedState = {};
static ImuData        s_cachedImuData = {};
static SemaphoreHandle_t s_imuMutex = NULL;
static TaskHandle_t   s_imuTaskHandle = NULL;

static MadgwickFilter s_madgwick;
static float s_currentBeta = BASE_BETA;

// Jerk spike state
static float s_prevTotalG = 1.0f;
static unsigned long s_lastImuTime = 0;

// Saturation state
static float s_lastValidSpeed = 0.0f;

// Throw/catch/impact timing states
static bool s_throwArmed = false;
static bool s_wasInFreeFall = false;
static bool s_throwFlag = false;
static bool s_catchFlag = false;
static bool s_impactFlag = false;
static unsigned long s_throwTime = 0;
static unsigned long s_catchTime = 0;
static unsigned long s_impactTime = 0;

// Accel scale: ±16g → 2048 LSB/g
static constexpr float ACC_SCALE = 2048.0f;
// Gyro scale: ±2000 dps → 16.4 LSB/dps
static constexpr float GYRO_SCALE = 16.4f;

static bool readRaw(int16_t &ax, int16_t &ay, int16_t &az,
                    int16_t &gx, int16_t &gy, int16_t &gz) {
    Wire.beginTransmission(IMU_ADDR);
    Wire.write(0x3B);
    if (Wire.endTransmission(false) != 0) return false;
    Wire.requestFrom(IMU_ADDR, (uint8_t)14);
    if (Wire.available() < 14) return false;
    ax=(Wire.read()<<8)|Wire.read(); ay=(Wire.read()<<8)|Wire.read();
    az=(Wire.read()<<8)|Wire.read();
    Wire.read(); Wire.read(); // temperature
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

static void imuTask(void *pvParameters) {
    TickType_t xLastWakeTime = xTaskGetTickCount();
    const TickType_t xFrequency = pdMS_TO_TICKS(1000 / IMU_SAMPLE_HZ); // 10ms (100Hz)
    while (true) {
        vTaskDelayUntil(&xLastWakeTime, xFrequency);
        ImuManager::update();
    }
}

bool ImuManager::init() {
    Wire.begin(IMU_SDA, IMU_SCL);
    Wire.setClock(400000);
    delay(50);
    writeReg(0x6B, 0x00); // wake up
    delay(10);
    
    // Configure full scale: gyro ±2000 dps (0x18), accel ±16g (0x18)
    writeReg(0x1B, 0x18);
    writeReg(0x1C, 0x18);

    uint8_t addrs[2] = {0x68, 0x69};
    bool found = false;
    for (int i = 0; i < 2; i++) {
        uint8_t addr = addrs[i];
        Wire.beginTransmission(addr);
        Wire.write(0x75); // WHO_AM_I
        Wire.endTransmission(false);
        Wire.requestFrom((uint8_t)addr, (uint8_t)1);
        uint8_t who = (Wire.available() > 0) ? Wire.read() : 0xFF;
        Serial.printf("I2C addr=0x%02X  WHO_AM_I=0x%02X\n", addr, who);
        if (who == 0x68 || who == 0x70) {
            found = true;
            break;
        }
    }
    if (!found) return false;

    s_madgwick.begin(IMU_SAMPLE_HZ);

    // Create Mutex and FreeRTOS task
    s_imuMutex = xSemaphoreCreateMutex();
    if (s_imuMutex == NULL) return false;

    s_lastImuTime = micros();

    xTaskCreatePinnedToCore(
        imuTask,
        "IMUTask",
        4096,
        NULL,
        1, // Priority
        &s_imuTaskHandle,
        0 // Core 0
    );

    return true;
}

bool ImuManager::isCalibrated() { return s_calibrated; }

bool ImuManager::calibrate() {
    int16_t ax, ay, az, gx, gy, gz;
    // Static detection: 10 samples must show near-zero rotation
    for (int i = 0; i < 10; i++) {
        if (!readRaw(ax, ay, az, gx, gy, gz)) return false;
        float spd = sqrtf((gx/GYRO_SCALE)*(gx/GYRO_SCALE) +
                          (gy/GYRO_SCALE)*(gy/GYRO_SCALE) +
                          (gz/GYRO_SCALE)*(gz/GYRO_SCALE)) * (float)M_PI / 180.0f;
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
    
    // Set RAM float offsets
    s_offGx_f = sGx/200.0f; 
    s_offGy_f = sGy/200.0f; 
    s_offGz_f = sGz/200.0f;
    s_offAx_f = sAx/200.0f; 
    s_offAy_f = sAy/200.0f;
    
    s_calibrated = true;
    Serial.printf("Cal: offG=(%.1f,%.1f,%.1f) offA=(%.1f,%.1f)\n",
                  s_offGx_f, s_offGy_f, s_offGz_f, s_offAx_f, s_offAy_f);
    return true;
}

void ImuManager::update() {
    int16_t raw_ax, raw_ay, raw_az;
    int16_t raw_gx, raw_gy, raw_gz;
    if (!readRaw(raw_ax, raw_ay, raw_az, raw_gx, raw_gy, raw_gz)) return;

    // Apply calibration offsets
    float gx_dps = (raw_gx - s_offGx_f) / GYRO_SCALE;
    float gy_dps = (raw_gy - s_offGy_f) / GYRO_SCALE;
    float gz_dps = (raw_gz - s_offGz_f) / GYRO_SCALE;

    float ax_g = (raw_ax - s_offAx_f) / ACC_SCALE;
    float ay_g = (raw_ay - s_offAy_f) / ACC_SCALE;
    float az_g = raw_az / ACC_SCALE; // AZ has gravity reference, no offset subtraction

    // 1. Gyro Saturation Check (OR logic on each axis)
    bool gyro_saturated = (fabsf(gx_dps) > GYRO_SAT_THRESH || 
                           fabsf(gy_dps) > GYRO_SAT_THRESH || 
                           fabsf(gz_dps) > GYRO_SAT_THRESH);

    float gx_rad = gx_dps * (float)M_PI / 180.0f;
    float gy_rad = gy_dps * (float)M_PI / 180.0f;
    float gz_rad = gz_dps * (float)M_PI / 180.0f;

    float raw_speed = sqrtf(gx_rad*gx_rad + gy_rad*gy_rad + gz_rad*gz_rad);
    float current_speed = raw_speed;
    if (!gyro_saturated) {
        s_lastValidSpeed = raw_speed;
    } else {
        current_speed = s_lastValidSpeed; // Dead Reckoning
    }

    // 2. Jerk-Based Spike Filter
    unsigned long now = micros();
    float dt = (now - s_lastImuTime) / 1000000.0f;
    s_lastImuTime = now;

    float total_g = sqrtf(ax_g*ax_g + ay_g*ay_g + az_g*az_g);
    float jerk = (dt > 0.0f) ? fabsf(total_g - s_prevTotalG) / dt : 0.0f;
    s_prevTotalG = total_g;
    
    bool is_spike = (jerk > JERK_SPIKE_THRESH);

    // 3. Accel Clipping & Freefall
    bool accel_clipped = (fabsf(ax_g) > ACCEL_CLIP_THRESH || 
                          fabsf(ay_g) > ACCEL_CLIP_THRESH || 
                          fabsf(az_g) > ACCEL_CLIP_THRESH);
    bool in_free_fall = (total_g < ACCEL_FREEFALL);

    // 4. Beta Ramping
    float target_beta = (accel_clipped || in_free_fall) ? CLIPPED_BETA : BASE_BETA;
    if (s_currentBeta < target_beta) {
        s_currentBeta = fminf(target_beta, s_currentBeta + BETA_RAMP_SPEED);
    } else if (s_currentBeta > target_beta) {
        s_currentBeta = fmaxf(target_beta, s_currentBeta - BETA_RAMP_SPEED);
    }
    s_madgwick.setBeta(s_currentBeta);

    // 5. Madgwick update (skip accel if spike detected)
    if (is_spike) {
        s_madgwick.updateIMU(gx_rad, gy_rad, gz_rad, 0.0f, 0.0f, 0.0f);
    } else {
        s_madgwick.updateIMU(gx_rad, gy_rad, gz_rad, ax_g, ay_g, az_g);
    }

    float pitch = s_madgwick.getPitch();
    float roll = s_madgwick.getRoll();

    // 6. Throw/Catch state machine
    if (current_speed > THROW_SPEED_MIN_RADS) {
        s_throwArmed = true;
    }
    if (!s_wasInFreeFall && in_free_fall && s_throwArmed) {
        s_throwFlag = true;
        s_throwTime = millis();
        s_throwArmed = false;
    }
    if (s_wasInFreeFall && !in_free_fall && total_g > CATCH_ACC_THRESHOLD_G) {
        s_catchFlag = true;
        s_catchTime = millis();
    }
    s_wasInFreeFall = in_free_fall;

    // Timeout-based reset of throw/catch flags after 200ms
    if (s_throwFlag && (millis() - s_throwTime > 200)) s_throwFlag = false;
    if (s_catchFlag && (millis() - s_catchTime > 200)) s_catchFlag = false;

    // 7. Impact flag
    bool nowImpact = (total_g > IMPACT_THRESHOLD_G);
    if (nowImpact) {
        s_impactFlag = true;
        s_impactTime = millis();
    }
    if (s_impactFlag && (millis() - s_impactTime > 200)) s_impactFlag = false;

    // 8. Spin Direction
    bool spin_cw = (current_speed > SPIN_SPEED_THRESHOLD) && (gz_dps > 0);

    // 9. Orientation
    uint8_t orient_flag = STAFF_FLAG_ORIENT_HORIZ;
    float absPitch = fabsf(pitch);
    if (absPitch < ORIENT_VERTICAL_DEG) {
        orient_flag = STAFF_FLAG_ORIENT_VERT;
    } else if (absPitch > ORIENT_INVERTED_DEG) {
        orient_flag = STAFF_FLAG_ORIENT_INV;
    }

    // Compile flags
    uint8_t flags = 0;
    if (s_throwFlag)   flags |= STAFF_FLAG_THROW;
    if (s_catchFlag)   flags |= STAFF_FLAG_CATCH;
    if (spin_cw)       flags |= STAFF_FLAG_SPIN_CW;
    flags |= orient_flag;
    if (s_impactFlag)  flags |= STAFF_FLAG_IMPACT;

    // 10. Dynamic Window
    float spin_speed_dps = current_speed * 180.0f / (float)M_PI;
    float half_window = WINDOW_MIN_DEG + (spin_speed_dps / SPIN_SPEED_MAX) * (WINDOW_MAX_DEG - WINDOW_MIN_DEG);
    if (half_window < WINDOW_MIN_DEG) half_window = WINDOW_MIN_DEG;
    if (half_window > WINDOW_MAX_DEG) half_window = WINDOW_MAX_DEG;

    // Write to thread-safe shared state
    if (s_imuMutex != NULL && xSemaphoreTake(s_imuMutex, 0) == pdTRUE) {
        s_sharedState.pitch = pitch;
        s_sharedState.roll = roll;
        s_sharedState.spin_speed = current_speed;
        s_sharedState.in_free_fall = in_free_fall;
        s_sharedState.gyro_saturated = gyro_saturated;
        s_sharedState.accel_clipped = accel_clipped;
        s_sharedState.accX = raw_ax - (int16_t)s_offAx_f;
        s_sharedState.accY = raw_ay - (int16_t)s_offAy_f;
        s_sharedState.accZ = raw_az;
        s_sharedState.gyroX = raw_gx - (int16_t)s_offGx_f;
        s_sharedState.gyroY = raw_gy - (int16_t)s_offGy_f;
        s_sharedState.gyroZ = raw_gz - (int16_t)s_offGz_f;
        s_sharedState.flags = flags;
        s_sharedState.half_window = half_window;
        xSemaphoreGive(s_imuMutex);
    }

    // 11. Continuous In-Use Calibration (bias estimate for thermal drift)
    float gyro_mag_dps = current_speed * 180.0f / (float)M_PI;
    bool accel_stable = (fabsf(total_g - 1.0f) < 0.1f) && (jerk < 5.0f);
    if (gyro_mag_dps < GYRO_STILL && accel_stable && !in_free_fall) {
        s_offGx_f = s_offGx_f * 0.999f + raw_gx * 0.001f;
        s_offGy_f = s_offGy_f * 0.999f + raw_gy * 0.001f;
        s_offGz_f = s_offGz_f * 0.999f + raw_gz * 0.001f;
    }
}

bool ImuManager::read(ImuData &out) {
    if (s_imuMutex != NULL) {
        if (xSemaphoreTake(s_imuMutex, 0) == pdTRUE) {
            s_cachedImuData.accX = s_sharedState.accX;
            s_cachedImuData.accY = s_sharedState.accY;
            s_cachedImuData.accZ = s_sharedState.accZ;
            s_cachedImuData.gyroX = s_sharedState.gyroX;
            s_cachedImuData.gyroY = s_sharedState.gyroY;
            s_cachedImuData.gyroZ = s_sharedState.gyroZ;
            s_cachedImuData.speed = s_sharedState.spin_speed;
            s_cachedImuData.angle = s_sharedState.pitch;
            s_cachedImuData.flags = s_sharedState.flags;
            xSemaphoreGive(s_imuMutex);
        }
    }
    out = s_cachedImuData;
    return true;
}

bool ImuManager::readState(SharedImuState &out) {
    static SharedImuState cachedState = {};
    if (s_imuMutex != NULL) {
        if (xSemaphoreTake(s_imuMutex, 0) == pdTRUE) {
            cachedState = s_sharedState;
            xSemaphoreGive(s_imuMutex);
        }
    }
    out = cachedState;
    return true;
}

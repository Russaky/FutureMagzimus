#pragma once

#define FIRMWARE_VERSION  "v1.0.1"

// LEDs
#define LED_PIN            10
#define NUM_LEDS           26
#define NUM_LEDS_PHYSICAL  130   // 5 strips × 26, zigzag
#define LED_MAX_BRIGHTNESS 216   // 85% of 255

// Virtual pixel layout (serpentine + gap)
// Two sections of 50 LEDs with a 100cm physical gap represented as virtual pixels
#ifndef NUM_LEDS_SECTION
#define NUM_LEDS_SECTION   50
#define GAP_VIRTUAL        20   // virtual pixels over the 100cm gap
#define NUM_LEDS_VIRTUAL   (NUM_LEDS_SECTION * 2 + GAP_VIRTUAL)  // 120
#endif

// IMU — pins overridden per-env in platformio.ini
#ifndef IMU_SDA
#define IMU_SDA           6
#endif
#ifndef IMU_SCL
#define IMU_SCL           7
#endif
#define IMU_ADDR          0x68

// Hub disconnection timeout: if no ESP-NOW ACK for this long, fall back to IMU default
#define HUB_TIMEOUT_MS    3000

// Extended telemetry thresholds
#define THROW_SPEED_MIN_RADS    4.0f    // minimum speed (rad/s) before throw detection arms
#define FREE_FALL_THRESHOLD_G   0.4f    // acc magnitude below this (fraction of g) = free-fall
#define CATCH_ACC_THRESHOLD_G   2.0f    // acc magnitude above this after free-fall = catch
#define SPIN_SPEED_THRESHOLD    2.0f    // minimum speed (rad/s) for spin_direction detection
#define IMPACT_THRESHOLD_G      4.0f    // acc magnitude above this = impact
#define ORIENT_VERTICAL_DEG     30.0f   // |pitch| within this → vertical
#define ORIENT_INVERTED_DEG     150.0f  // |pitch| beyond this → inverted

// CMD_LED_VERTICAL preset: |pitch| within this of vertical-up (0°) → green, else blue
#define LED_VERTICAL_GREEN_WINDOW_DEG  20.0f

// Complementary filter weight for tilt angle (gyro-predicted vs accel-reference).
// Closer to 1.0 → trusts gyro more (smooth, but drifts); closer to 0 → trusts accel more (noisy, no drift).
#define COMP_FILTER_ALPHA       0.98f

// IMU Motion Detection constants
#define BASE_BETA            0.1f
#define CLIPPED_BETA         0.0f
#define BETA_RAMP_SPEED      0.005f
#define GYRO_SAT_THRESH      1950.0f  // dps
#define ACCEL_CLIP_THRESH    15.5f   // g
#define ACCEL_FREEFALL       0.3f     // g
#define GYRO_STILL           5.0f     // dps
#define JERK_SPIKE_THRESH    50.0f   // g/s
#define IMU_SAMPLE_HZ        100

#define DWELL_SLOW_THRESH    80.0f   // dps
#define DWELL_MIN_MS         200     // ms
#define ROTATION_DEBOUNCE    50      // ms

#define WINDOW_MIN_DEG       10.0f   // °
#define WINDOW_MAX_DEG       60.0f   // °
#define SPIN_SPEED_MAX       2000.0f // dps

// ESP-NOW
#define ESPNOW_CHANNEL    1
#define QUEUE_SIZE        10
#define TELEMETRY_MS      50

// Network discovery
#define DISCOVERY_PORT    5555
#ifndef DEVICE_ROLE
#define DEVICE_ROLE       "staff"
#endif
#ifndef OTA_HOSTNAME
#define OTA_HOSTNAME      "magzimus-device"
#endif
#ifndef OTA_PASSWORD
#define OTA_PASSWORD      "magzimus"
#endif

// DMX fixture mirroring the Staff's own active LED color (see main.cpp)
#define DMX_MIRROR_ADDR   1

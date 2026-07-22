#pragma once

#define FIRMWARE_VERSION  "v1.0"

#ifndef NODE_ID
#define NODE_ID  1   // 1-4, fixed at compile time (see platformio.ini envs)
#endif

// WRGB GPIO pins (LEDC channels 0-3)
#if defined(ESP32_C3)
#define PWM_PIN_R  0
#define PWM_PIN_G  1
#define PWM_PIN_B  2
#define PWM_PIN_W  3
#elif defined(ESP32_S3)
#define PWM_PIN_W  4
#define PWM_PIN_R  5
#define PWM_PIN_G  6
#define PWM_PIN_B  7
#else
#define PWM_PIN_W  16
#define PWM_PIN_R  17
#define PWM_PIN_G  18
#define PWM_PIN_B  19
#endif

#define PWM_FREQ   1000   // Hz (LEDC, per Light Nodes spec)
#define PWM_BITS   8      // resolution (0-255)

#define ESPNOW_CHANNEL  1
#define QUEUE_SIZE      5

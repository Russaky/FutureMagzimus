#pragma once

#define FIRMWARE_VERSION  "v1.0"

// WRGB GPIO pins (LEDC channels 0-3)
#define PWM_PIN_W  16
#define PWM_PIN_R  17
#define PWM_PIN_G  18
#define PWM_PIN_B  19

#define PWM_FREQ   5000   // Hz
#define PWM_BITS   8      // resolution (0-255)

#define ESPNOW_CHANNEL  1
#define QUEUE_SIZE      5

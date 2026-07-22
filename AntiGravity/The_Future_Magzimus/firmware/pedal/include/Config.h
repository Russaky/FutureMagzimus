#pragma once

#define FIRMWARE_VERSION      "v1.0"

#define BUTTON_PIN            5     // microswitch input (INPUT_PULLUP)
#define STATUS_LED_RED_PIN    13
#define STATUS_LED_GREEN_PIN  12
#define STATUS_LED_YELLOW_PIN 14

// Timing thresholds (milliseconds)
#define SHORT_THRESHOLD_MS    300
#define LONG_THRESHOLD_MS     700
#define DOUBLE_WINDOW_MS      400
#define TRIPLE_WINDOW_MS      600

#define DEBOUNCE_MS           20
#define ESPNOW_CHANNEL        1
#ifndef OTA_HOSTNAME
#define OTA_HOSTNAME          "pedal"
#endif
#define OTA_PASSWORD          "magzimus"

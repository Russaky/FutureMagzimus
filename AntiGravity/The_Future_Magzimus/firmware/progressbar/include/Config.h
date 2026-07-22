#pragma once

#define FIRMWARE_VERSION  "v1.0"
#define LED_PIN           8       // GPIO 8 on C3
#define NUM_LEDS          100
#define LED_MAX_BRIGHTNESS 220

#define ESPNOW_CHANNEL    1
#ifndef OTA_HOSTNAME
#define OTA_HOSTNAME      "progressbar-c3"
#endif
#define OTA_PASSWORD      "magzimus"

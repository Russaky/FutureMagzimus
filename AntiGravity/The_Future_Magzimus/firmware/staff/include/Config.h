#pragma once

#define FIRMWARE_VERSION  "v1.0"

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

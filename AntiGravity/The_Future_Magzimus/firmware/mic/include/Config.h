#pragma once

#define FIRMWARE_VERSION   "v1.1"

#ifndef MIC_ADC_PIN
#define MIC_ADC_PIN        0       // MAX9814 OUT → ADC1 pin. ESP32-C3 default: GPIO0.
#endif                              // ESP32-S3: GPIO4 (set via -D MIC_ADC_PIN=4 in env:mic-s3).
#define SAMPLE_RATE        8000    // Hz
#define FFT_WINDOW_SIZE    256     // must be power of 2
#define TELEMETRY_MS       50      // send interval

#define ESPNOW_CHANNEL     1
#ifndef OTA_HOSTNAME
#define OTA_HOSTNAME       "mic-c3"
#endif
#define OTA_PASSWORD       "magzimus"

#pragma once

#define FIRMWARE_VERSION  "v1.1"
#define ESPNOW_CHANNEL    1
#define QUEUE_SIZE        5

// DMX512 (MAX485)
#define DMX_PORT_NUM      DMX_NUM_1
#define DMX_TX_PIN        2   // DI of MAX485
#define DMX_RX_PIN        DMX_PIN_NO_CHANGE  // unused — TX only
#define DMX_ENABLE_PIN    1   // RE+DE tied together, held HIGH (always transmit)

// Target frame rate: ~40Hz
#define FRAME_INTERVAL_MS 25

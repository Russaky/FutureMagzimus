#pragma once
#include <stdint.h>

using SerialCommandCb = void(*)(uint8_t msgType, const uint8_t *payload, uint16_t len);

class SerialBridge {
public:
    static void begin(uint32_t baud, SerialCommandCb cb);
    static void sendFrame(uint8_t msgType, const uint8_t *payload, uint16_t len);
    static void poll();
};

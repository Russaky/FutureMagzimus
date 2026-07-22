#pragma once
#include "Protocol.h"

class EspNow {
public:
    static uint8_t deviceId;  // = NODE_ID
    static void    init();
    static bool    dequeue(light_cmd_t &out);
    static void    sendAck(uint8_t w, uint8_t r, uint8_t g, uint8_t b);
};

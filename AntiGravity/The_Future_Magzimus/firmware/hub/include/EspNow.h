#pragma once
#include <stdint.h>

class EspNow {
public:
    static void init();
    static void send(const uint8_t *payload, uint16_t len);
    static void sendDiscover();
    static void sendAlive();
};

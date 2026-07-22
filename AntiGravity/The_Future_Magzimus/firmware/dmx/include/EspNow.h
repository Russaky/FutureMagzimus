#pragma once
#include "Protocol.h"

class EspNow {
public:
    static uint16_t deviceId;  // last 2 bytes of MAC
    static void     init();
    static bool     dequeue(DMXCommand &out);
    // Call once per loop() iteration: sends the identity response from safe
    // task context if a DiscoverRequest arrived since the last call (never
    // call esp_now_send() directly from the recv callback — see EspNow.cpp).
    static void     pollDiscover();
};

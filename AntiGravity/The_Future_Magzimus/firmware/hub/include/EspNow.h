#pragma once
#include <stdint.h>

class EspNow {
public:
    static void init();
    static void send(const uint8_t *payload, uint16_t len);
    static void sendDiscover();
    static void sendAlive();
    static void wifiJoin();   // join the same network as Staff during OTA
    static void wifiLeave();  // return to standalone ESP-NOW channel
};

#pragma once
#include "Protocol.h"

class EspNow {
public:
    static uint8_t deviceId;  // last byte of MAC
    static void    init();
    static bool    dequeue(RelayCommand &out);
};

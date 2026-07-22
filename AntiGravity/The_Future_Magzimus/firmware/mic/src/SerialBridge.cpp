#include "SerialBridge.h"
#include <Arduino.h>

static SerialCommandCb _cb = nullptr;

// CRC-8/SMBUS (poly 0x07)
static uint8_t crc8(const uint8_t *data, size_t len, uint8_t crc = 0) {
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++)
            crc = (crc & 0x80) ? (crc << 1) ^ 0x07 : (crc << 1);
    }
    return crc;
}

// ─── Parser state machine ─────────────────────────────────────────────────────
enum ParseState : uint8_t {
    WAIT_H1, WAIT_H2, READ_TYPE, READ_LEN_L, READ_LEN_H, READ_PAYLOAD, READ_CRC
};

static ParseState  _state      = WAIT_H1;
static uint8_t     _msgType    = 0;
static uint16_t    _payloadLen = 0;
static uint16_t    _payloadIdx = 0;
static uint8_t     _payload[256];

void SerialBridge::begin(uint32_t baud, SerialCommandCb cb) {
    Serial.begin(baud);
    _cb = cb;
}

void SerialBridge::sendFrame(uint8_t msgType, const uint8_t *payload, uint16_t len) {
    uint8_t meta[3] = {msgType, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8)};
    uint8_t chk = crc8(meta, 3);
    chk = crc8(payload, len, chk);

    Serial.write((uint8_t)0xAA);
    Serial.write((uint8_t)0x55);
    Serial.write(meta, 3);
    Serial.write(payload, len);
    Serial.write(chk);
}

void SerialBridge::poll() {
    while (Serial.available()) {
        uint8_t b = Serial.read();
        switch (_state) {
            case WAIT_H1:
                _state = (b == 0xAA) ? WAIT_H2 : WAIT_H1;
                break;
            case WAIT_H2:
                _state = (b == 0x55) ? READ_TYPE : WAIT_H1;
                break;
            case READ_TYPE:
                _msgType = b;
                _state = READ_LEN_L;
                break;
            case READ_LEN_L:
                _payloadLen = b;
                _state = READ_LEN_H;
                break;
            case READ_LEN_H:
                _payloadLen |= (uint16_t)b << 8;
                _payloadIdx = 0;
                _state = (_payloadLen == 0) ? READ_CRC : READ_PAYLOAD;
                break;
            case READ_PAYLOAD:
                if (_payloadIdx < sizeof(_payload))
                    _payload[_payloadIdx++] = b;
                if (_payloadIdx >= _payloadLen)
                    _state = READ_CRC;
                break;
            case READ_CRC: {
                uint8_t meta[3] = {_msgType, (uint8_t)(_payloadLen & 0xFF), (uint8_t)(_payloadLen >> 8)};
                uint8_t expected = crc8(meta, 3);
                expected = crc8(_payload, _payloadLen, expected);
                if (b == expected && _cb)
                    _cb(_msgType, _payload, _payloadLen);
                _state = WAIT_H1;
                break;
            }
        }
    }
}

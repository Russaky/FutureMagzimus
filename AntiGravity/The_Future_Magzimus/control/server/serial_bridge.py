"""Non-blocking Serial reader — parses framed packets from Hub."""
from __future__ import annotations
import threading
import struct
import serial
from enum import IntEnum
from typing import Callable

import protocol as proto


class _S(IntEnum):
    WAIT_H1 = 0; WAIT_H2 = 1; READ_TYPE = 2
    READ_LEN_L = 3; READ_LEN_H = 4; READ_PAYLOAD = 5; READ_CRC = 6


class SerialBridge:
    def __init__(self, port: str, baud: int,
                 on_telemetry: Callable[[dict], None],
                 on_identity:  Callable[[dict], None] | None = None):
        self._ser = serial.Serial(port, baud, timeout=0.05)
        self._on_telemetry = on_telemetry
        self._on_identity  = on_identity
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._lock = threading.Lock()
        self._reset()

    def start(self):
        self._thread.start()

    def send(self, frame: bytes):
        with self._lock:
            self._ser.write(frame)

    def close(self):
        self._ser.close()

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _reset(self):
        self._state   = _S.WAIT_H1
        self._msg_type    = 0
        self._payload_len = 0
        self._payload     = bytearray()

    def _run(self):
        while True:
            try:
                chunk = self._ser.read(64)
                for b in chunk:
                    self._parse(b)
            except serial.SerialException:
                break

    def _parse(self, b: int):
        s = self._state
        if s == _S.WAIT_H1:
            if b == 0xAA: self._state = _S.WAIT_H2
        elif s == _S.WAIT_H2:
            self._state = _S.READ_TYPE if b == 0x55 else _S.WAIT_H1
        elif s == _S.READ_TYPE:
            self._msg_type = b; self._state = _S.READ_LEN_L
        elif s == _S.READ_LEN_L:
            self._payload_len = b; self._state = _S.READ_LEN_H
        elif s == _S.READ_LEN_H:
            self._payload_len |= b << 8
            self._payload = bytearray()
            self._state = _S.READ_CRC if self._payload_len == 0 else _S.READ_PAYLOAD
        elif s == _S.READ_PAYLOAD:
            self._payload.append(b)
            if len(self._payload) >= self._payload_len:
                self._state = _S.READ_CRC
        elif s == _S.READ_CRC:
            meta     = bytes([self._msg_type]) + struct.pack('<H', self._payload_len)
            expected = proto._crc8(meta + bytes(self._payload))
            if b == expected:
                self._dispatch(self._msg_type, bytes(self._payload))
            self._reset()

    def _dispatch(self, msg_type: int, payload: bytes):
        if msg_type == proto.MSG_STAFF_TELEMETRY:
            data = proto.parse_staff_telemetry(payload)
            if data:
                self._on_telemetry(data)
        elif msg_type == proto.MSG_IDENTITY:
            data = proto.parse_identity(payload)
            if data and self._on_identity:
                self._on_identity(data)
        elif msg_type == proto.MSG_AUTONOMOUS:
            data = proto.parse_autonomous(payload)
            if data and self._on_identity:
                self._on_identity({**data, 'role': 'autonomous_event'})

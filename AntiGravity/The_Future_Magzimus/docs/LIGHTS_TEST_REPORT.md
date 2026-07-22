# Lights System Test Report — 2026-06-29

**Result: 26/28 passed** | 2 failed

## Results

| Status | Test | Detail |
|--------|------|--------|
| ✅ | Bridge/Node share light_cmd_t / light_ack_t layout |  |
| ✅ | light_cmd_t / light_ack_t pack to 5 bytes | cmd=5 ack=5 |
| ✅ | light_cmd_t round-trip pack/unpack |  |
| ✅ | extractIntField parses | {"target":1,"r":255,"g":0,"b":0,"w":0} -> {'target': 1, 'r': 255, 'g': 0, 'b': 0, 'w': 0} |
| ✅ | extractIntField parses | {"target":0,"r":0,"g":0,"b":0,"w":0} -> {'target': 0, 'r': 0, 'g': 0, 'b': 0, 'w': 0} |
| ✅ | extractIntField parses | {"r":128,"target":4} -> {'target': 4, 'r': 128, 'g': 0, 'b': 0, 'w': 0} |
| ✅ | extractIntField parses | {} -> {'target': 0, 'r': 0, 'g': 0, 'b': 0, 'w': 0} |
| ✅ | Bridge uses minimal JSON extraction (no ArduinoJson dependency) |  |
| ✅ | target=0 (broadcast) arms timeout tracking for all 4 nodes |  |
| ✅ | Timeout fires only for nodes that did not ACK | ['[TIMEOUT] Node 1', '[TIMEOUT] Node 3', '[TIMEOUT] Node 4'] |
| ✅ | No premature timeout before 200ms elapsed |  |
| ✅ | Timeout fires at exactly 200ms threshold |  |
| ✅ | Bridge: fixed ESP-NOW channel constant |  |
| ✅ | Bridge: AP fallback SSID/password = MagLight/magzimus |  |
| ✅ | Bridge: per-network timeout before AP fallback |  |
| ✅ | Bridge: serves HTML console at / |  |
| ✅ | Bridge: /color HTTP endpoint |  |
| ✅ | Bridge: Serial JSON line interface |  |
| ✅ | Bridge: 200ms ACK timeout |  |
| ✅ | Bridge: ESP-NOW recv callback only buffers (no heavy work in ISR) |  |
| ✅ | Node: NODE_ID fixed at compile time (1-4) |  |
| ✅ | Node: PWM 1kHz, 8-bit |  |
| ✅ | Node: GPIO pulled low immediately on boot |  |
| ✅ | Node: duplicate command -> no action, no ACK |  |
| ✅ | Node: ACK sent only on state change |  |
| ✅ | Fire-and-forget: no retry logic present (per spec) |  |
| ❌ | Bridge not found on any candidate serial port | ['/dev/cu.usbmodem1234561', '/dev/cu.usbmodem1434201'] |
| ❌ | BRIDGE_IP not set | export BRIDGE_IP=<bridge IP> (e.g. 192.168.4.1 on MagLight AP) to run this section |

## Summary

- **Tested on:** 2026-06-29
- **Pass:** 26
- **Fail:** 2

## Notes

- Sections 1-4 are unit/static tests — no hardware required.
- Section 5 requires a Bridge (ESP32) on a `/dev/cu.usbmodem*` / `/dev/cu.usbserial*` port running the Bridge firmware.
- Section 6 requires `BRIDGE_IP` env var set to the Bridge's IP (AP mode: `192.168.4.1` on SSID `MagLight`).
- `credentials.h` currently has empty SSID/password placeholders — Bridge will always fall back to AP-only mode until venue/home WiFi is filled in.

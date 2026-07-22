# Protocol Test Report — 2026-06-07

**Result: 19/20 passed** | 1 failed

## Results

| Status | Test | Detail |
|--------|------|--------|
| ✅ | CRC of empty input is 0 |  |
| ✅ | CRC matches packed frame |  |
| ✅ | Tampered payload detected by CRC |  |
| ✅ | pack_staff_command | type=0x10 len=8 |
| ✅ | pack_relay_command | type=0x11 len=5 |
| ✅ | pack_pwm_command | type=0x12 len=8 |
| ✅ | pack_wifi_ctrl | type=0x30 len=4 |
| ✅ | pack_role_ctrl | type=0x31 len=5 |
| ✅ | pack_discover | type=0x20 len=1 |
| ✅ | parse_staff_telemetry | id=028C angle=45.7° speed=1.234 throw=True |
| ✅ | parse_identity | id=028C role=staff fw=v1.0 |
| ✅ | pack_role_ctrl (txEnabled=False) | groupId=1 msgType=0x31 targetId=028C txEn=0 |
| ✅ | pack_role_ctrl (txEnabled=True) |  |
| ✅ | IGNORE policy: second dropped |  |
| ✅ | QUEUE policy: second runs after first |  |
| ✅ | INTERRUPT policy: second preempts first |  |
| ✅ | set_slot / list_slots |  |
| ✅ | hotswap: slot updated to new deviceId |  |
| ✅ | hotswap: other slot unchanged |  |
| ❌ | Live test exception | [Errno 16] could not open port /dev/cu.usbserial-0001: [Errno 16] Resource busy: '/dev/cu.usbserial-0001' |

## Summary

- **Tested on:** 2026-06-07
- **Hub port:** `/dev/cu.usbserial-0001`
- **Pass:** 19
- **Fail:** 1

## Notes

- Unit tests run without hardware (CRC, framing, registry, slots)
- Live tests require Hub on `/dev/cu.usbserial-0001` with both Staffs in ESP-NOW range
- `HUB_TIMEOUT_MS = 3000` — Staff falls back to IMU after 3s without ACK
- Role assignment persisted to NVS; default `tx_enabled = true`

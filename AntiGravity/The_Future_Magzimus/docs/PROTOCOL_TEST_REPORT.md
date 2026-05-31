# Protocol Test Report — 2026-05-31

**Result: 36/36 passed** | 0 failed

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
| ✅ | parse_staff_telemetry | id=028C angle=8.4° speed=0.110 |
| ✅ | parse_identity | id=028C role=staff fw=v1.0 |
| ✅ | pack_role_ctrl (txEnabled=False) | groupId=1 msgType=0x31 targetId=028C txEn=0 |
| ✅ | pack_role_ctrl (txEnabled=True) |  |
| ✅ | IGNORE policy: second dropped |  |
| ✅ | QUEUE policy: second runs after first |  |
| ✅ | INTERRUPT policy: second preempts first |  |
| ✅ | set_slot / list_slots |  |
| ✅ | hotswap: slot updated to new deviceId |  |
| ✅ | hotswap: other slot unchanged |  |
| ✅ | Serial bridge opened | /dev/cu.usbserial-0001 |
| ✅ | Telemetry received | 2 sender(s): ['AD44', '028C'] |
| ✅ | Discover: 2 devices responded | ['AD44', '028C'] |
| ✅ | Telemetry continues after LED_SOLID command |  |
| ✅ | LED_OFF sent successfully |  |
| ✅ | Role ctrl broadcast sent (tx=enabled) |  |
| ✅ | Telemetry sanity id=AD44 | angle=-86.3° speed=0.067 |
| ✅ | Telemetry sanity id=028C | angle=25.4° speed=0.110 |
| ✅ | CMD_LED_SPARKLE sent + telemetry active |  |
| ✅ | CMD_LED_FLAME sent + telemetry active |  |
| ✅ | CMD_LED_RAINBOW sent + telemetry active |  |
| ✅ | LED_OFF after effects |  |
| ✅ | targetSlot undefined → timeline skipped |  |
| ✅ | targetSlot=AD44 → timeline fired to AD44 |  |
| ✅ | hotswap AD44→028C: timeline redirected |  |
| ✅ | ROLE_CTRL txEnabled=false: AD44 stopped tx |  |
| ✅ | ROLE_CTRL txEnabled=true: AD44 resumed tx |  |

## Summary

- **Tested on:** 2026-05-31
- **Hub port:** `/dev/cu.usbserial-0001`
- **Pass:** 36
- **Fail:** 0

## Notes

- Unit tests run without hardware (CRC, framing, registry, slots)
- Live tests require Hub on `/dev/cu.usbserial-0001` with both Staffs in ESP-NOW range
- `HUB_TIMEOUT_MS = 3000` — Staff falls back to IMU after 3s without ACK
- Role assignment persisted to NVS; default `tx_enabled = true`

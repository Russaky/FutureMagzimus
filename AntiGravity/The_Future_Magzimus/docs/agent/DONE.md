# DONE — לוג משימות שבוצעו

## [2026-05-28] הקמת תשתית פרויקט
נוצר מבנה תיקיות מלא + קבצי ניהול סוכן. שולב orchestrator.py + tasks.json בתהליך העבודה.

## [2026-05-28] למידת פרויקט ייחוס (Smart_Staff)
נסרק Ver_Beta/BT_setup — חולצו ESP-NOW, BLE, OTA, מבנה תפקידים.

## [2026-05-28] Staff Firmware
firmware/staff/ — ESP32-S3, FastLED, Wire (hardware I2C).
פרוטוקול: StaffTelemetry (24 bytes) → Hub כל 50ms | HubCommand (8 bytes) ← Hub.

## [2026-05-28] Hub Firmware
firmware/hub/ — ESP32-S3, Serial↔ESP-NOW bridge.
פרוטוקול Serial: [0xAA][0x55][type][len×2][payload][CRC8].

## [2026-05-28] Relay Firmware
firmware/relay/ — ESP32, GPIO 26, auto-shutoff לפי durationMs.

## [2026-05-28] PWM Firmware
firmware/pwm/ — ESP32, LEDC channels 0-3 (W/R/G/B), fade לינארי.

## [2026-05-28] Flask Control Server + Engine + UI
control/server/, control/engine/, control/ui/, numbers/example.json.

## [2026-05-29] ESP-NOW Dynamic WiFi Provisioning
MSG_WIFI_CTRL=0x30 בפרוטוקול. Hub מעביר פקודה לכל הבקרים. Staff מחובר WiFi רק כשמבקשים — כבוי ברירת מחדל, auto-off אחרי 10 דקות. Flasher: כפתורי WiFi ON/OFF + auto-scan אחרי הדלקה. Control server: /api/wifi endpoint.

ESP-NOW Device Discovery: MSG_DISCOVER/MSG_IDENTITY. Hub משדר DiscoverRequest, כל בקר עונה עם role/deviceId/firmware/IP. Flasher צולב נתונים דרך control server.

## [2026-05-29] Hot-Swapping Replacement Protocol
`control/engine/device_registry.py` — נוסף slot registry: `set_slot(slot, deviceId)`, `hotswap(slot, newId)` (מבטל timelines פעילים/ממתינים של הבקר הישן), `resolve(slot)`, `list_slots()`.
`control/engine/engine.py` — `_fire_event` תומך עכשיו ב-`targetSlot` בנוסף ל-`targetId`. אם ה-slot לא מוגדר — הטיימליין מדולג.
`control/server/app.py` — נוספו endpoints: `GET/POST /api/slots`, `POST /api/hotswap`.
**שימוש**: POST `/api/slots` להגדיר slot, POST `/api/hotswap` להחליף מכשיר בזמן אמת.

## [2026-05-29] Dual-Head Staff Architecture
`firmware/staff/include/Config.h` — `ROLE_PIN = 0` (GPIO 0).
`firmware/staff/include/LedManager.h` + `src/LedManager.cpp` — `solidMirrored()`: כמו `solid()` אבל עם `applyZigzagMirrored()` — סדר LED הפוך לראש השני של הסטאף.
`firmware/staff/src/main.cpp` — זיהוי תפקיד בזמן boot: `ROLE_PIN LOW` → Rx-Only (ללא IMU, ללא telemetry, LEDs עם mirroring). `ROLE_PIN HIGH` (pullup) → Tx (התנהגות רגילה).
**שימוש**: חיבור ROLE_PIN לGND בראש ה-Rx.

## [2026-05-31] RF Optimization + Pairing + Dual-Head SM + Gyro Cal + Virtual Pixels
**RF:** `esp_wifi_set_max_tx_power(80)` + `WIFI_PHY_RATE_1M_L` ב-EspNow.cpp — טווח מקסימלי.
**Gyroscope Calibration:** `ImuManager::calibrate()` — 200 דגימות ב-500ms, offsets ב-RAM, guard תנועה. `CMD_CALIBRATE=6`.
**Virtual Pixels & Serpentine:** `LedManager::XY(virtualIdx)` — Section A (0-49) → gap (50-69=null) → Section B (99-50, reverse). `NUM_LEDS_VIRTUAL=120`.
**Pairing & Provisioning:** `PairingRequest` (MSG_PAIR_REQ=0x40) בboot + `PairingAck` מה-Hub עם Hub MAC. STAFF_ID ב-NVS.
**Dual-Head State Machine:** Slave מקבל `SyncPacket` (MSG_SYNC=0x50) מ-Master כל 50ms. Fallback ל-IMU אחרי 500ms ללא sync. Master שולח tilt/effect state לSlave ב-broadcast.
**OTA fix:** `ArduinoOTA.onError()` → `wifiDisable()` אוטומטי. `WIFI_AUTO_OFF_MS` הצטמצם ל-2 דקות.

## [2026-05-28] Flasher Tool
tools/flasher/ — Flask-SocketIO על פורט 5001.
בוחרים firmware (hub/staff/relay/pwm), port USB, לוחצים Build או Build+Flash.
הפלט מוזרם בזמן אמת לטרמינל בדפדפן. pio נמצא אוטומטית.

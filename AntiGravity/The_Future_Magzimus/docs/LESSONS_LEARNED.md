# Lessons Learned — TheFutureMAGZIMUS
## Push: feat/full-MVP + protocol test suite

---

## 1. ESP-NOW ↔ WiFi Channel Conflict

### האתגר
כשה-Staff מתחבר ל-WiFi לצורך OTA, הוא עובר לערוץ ה-AP. מאותו רגע, ESP-NOW שלו עובר גם הוא לאותו ערוץ — ולא channel 1 שבו ה-Hub. התוצאה: חיתוך מלא של ESP-NOW עד ריבוט.

### הבעיה הספציפית
```
Staff connects to WiFi (AP channel 6)
  → ESP-NOW channel shifts to 6
  → Hub (channel 1) can't reach Staff
  → No OTA error = no recovery
  → Staff stuck on WiFi until physical reboot
```

### הפתרון
1. **ArduinoOTA.onError() callback** → קורא ל-`wifiDisable()` אוטומטית אם ה-OTA נכשל.
2. **WIFI_AUTO_OFF_MS** הצטמצם מ-10 דקות ל-2 דקות.
3. **`wifiDisable()` הוזז לפני `wifiEnable()`** בקוד — C++ לא מאפשר forward reference בתוך lambda.

### הלקח
> בכל מנגנון WiFi על ESP32 עם ESP-NOW: תמיד תכנן recovery path. הוסף timeout קצר + error callback. אל תסמוך על OTA שיצליח.

---

## 2. Hub Heartbeat — broadcast ACK תמיד מצליח

### האתגר
`isHubAlive()` בנוי על `esp_now_send_cb` שמעדכן `s_lastAckMs`. הרעיון: אם Hub לא ACK-ים → Hub מת. הבעיה: **ESP-NOW broadcast לעולם לא נכשל**. הcallback תמיד מחזיר `ESP_NOW_SEND_SUCCESS` ללא קשר לנמענים בפועל.

### הבעיה הספציפית
```cpp
static void onSent(const uint8_t *, esp_now_send_status_t status) {
    if (status == ESP_NOW_SEND_SUCCESS)
        s_lastAckMs = millis();  // ← תמיד מתעדכן, גם בלי Hub
}
```
Staff שולח telemetry broadcast כל 50ms → `s_lastAckMs` מתעדכן כל 50ms → `isHubAlive()` תמיד `true`.

### הפתרון
שני שינויים:
1. **Hub שולח `MSG_HUB_ALIVE` broadcast כל שנייה** — packet ייחודי (2 bytes).
2. **Staff מעדכן `s_lastAckMs` אך ורק עם קבלת HubAlive** — ה-`onSent` callback נותר ריק.

```cpp
static void onSent(const uint8_t *, esp_now_send_status_t status) {
    (void)status;  // intentionally empty — driven by MSG_HUB_ALIVE only
}
```

### הלקח
> ESP-NOW broadcast הוא fire-and-forget. לעולם אל תסמוך על onSent כאינדיקטור ל-Hub presence. השתמש בpacket-level heartbeat שהנמען שולח.

---

## 3. בדיקת Heartbeat בלי לנתק חומרה

### האתגר
לבדוק שה-Staff חוזר ל-IMU כשה-Hub מת — ניתוק פיזי של USB בכל פעם הוא איטי, לא ניתן לאוטומציה, ולא בר-חזרה.

### הפתרון
**MSG_HUB_PAUSE** — פקודה מהServer שמפסיקה את שידורי HubAlive לN שניות:

```python
POST /api/hub/pause  {"seconds": 10}
```

Hub מגיב:
```cpp
case MSG_HUB_PAUSE:
    if (len >= 1) pauseUntilMs = millis() + (uint32_t)payload[0] * 1000; break;
```

**MSG_AUTONOMOUS** — כשה-Staff זוהה ניתוק, הוא מכריז via ESP-NOW → Hub מעביר לMac → WebSocket event.

```
Hub paused at t=3s
  → Staff detects no HubAlive at t=6s (3s timeout)
  → Staff announces: autonomous, state=hub_lost
  → Hub forwards MSG_AUTONOMOUS to Mac
  → Server emits WebSocket event
```

**תוצאה בפועל:**
```
[5.1s] ★ 028C → autonomous
[5.1s] ★ AD44 → autonomous
[13.1s] ★ 028C → restored
[13.1s] ★ AD44 → restored
```

### הלקח
> בדיקת connectivity mechanisms — תמיד בנה software-controlled isolation. ניתוק פיזי אינו ניתן לאוטומציה ואינו חוזר על עצמו. הוסף observability (announce) מהרגע הראשון.

---

## 4. build_flags ב-PlatformIO לא מצטברים

### האתגר
WiFi credentials נשמרו ב-`wifi_credentials.ini` תחת `[env]` עם `build_flags`. הממשק עדכן, אבל הקוד כלל לא קיבל את ה-`WIFI_SSID` define.

### הסיבה
בPlatformIO, `build_flags` ב-`[env:staff]` **מחליף** (לא מצטרף) את `build_flags` ב-`[env]`. הקובץ החיצוני לא עקף את הenv הספציפי.

### הפתרון
החלפה ל-`build_src_flags` — שמצטרפים לדגלים הקיימים:
```ini
[env]
build_src_flags =
    '-D WIFI_SSID="MyNetwork"'
    '-D WIFI_PASSWORD="secret"'
```

### הלקח
> ב-PlatformIO: `build_flags` מחליף. `build_src_flags` מצטרף. לincludes חיצוניים שצריכים להיות global — השתמש תמיד ב-`build_src_flags`.

---

## 5. upload_flags גלובלי פגע ב-USB flash

### האתגר
`upload_flags = --auth=magzimus` נוסף ל-`[env]` כדי לתמוך ב-OTA auth. כשניסו לצרוב דרך USB, esptool קרס:
```
esptool: error: unrecognized arguments: --auth=magzimus
```

### הסיבה
`upload_flags` ב-`[env]` גלובלי חל על **כל** הenvironments, כולל USB. `--auth` הוא flag של `espota`, לא של `esptool`.

### הפתרון
העברת `upload_flags` לenvs של OTA בלבד:
```ini
[env:staff-ota]
upload_flags = --auth=magzimus

[env:staff-c3-ota]
upload_flags = --auth=magzimus
```

### הלקח
> `upload_flags` גלובלי שובר USB flashing. כל upload tool מקבל args שונים — הגדר תמיד per-env.

---

## 6. שינוי struct size שבר Protocol compatibility

### האתגר
הוספת `msgType` ל-`RoleCtrlCommand` שינתה אותו מ-4 bytes ל-5 bytes. Server שלח 5 bytes. Hub ישן ציפה ל-4 bytes ← drop שקט. ה-ROLE_CTRL לא עבד.

### מה קרה
```
Server → pack_role_ctrl() → 5 bytes
Hub (old firmware) → sizeof(RoleCtrlCommand) == 4 → drops packet
Staff → never receives → stays transmitting
test-03: FAIL
```

זוהה רק אחרי שינוי Hub firmware וצריבה מחדש.

### הלקח
> כל שינוי בגודל struct מחייב צריבה **של כל הרכיבים** (Hub + Staff) בו-זמנית. ב-ESP-NOW/Serial protocol — versioning אינו ב-goodwill, הוא חובה.

---

## 7. IMU WHO_AM_I: MPU6050 vs MPU6500

### האתגר
קוד המתין ל-WHO_AM_I = `0x68` (MPU6050). ה-IMU על ה-C3 החזיר `0x70` → init נכשל → אין telemetry.

### הסיבה
MPU6500 (variant זול נפוץ) מחזיר WHO_AM_I = `0x70`. פרוטוקול I2C ורגיסטרים זהים לחלוטין ל-MPU6050.

### הפתרון
```cpp
if (who == 0x68 || who == 0x70) return true;  // 0x68=MPU6050, 0x70=MPU6500
```

### הלקח
> אל תבדוק WHO_AM_I exact match ב-production code. בדוק family compatibility. תמיד הדפס את הערך ב-debug כדי לאבחן vendor variants.

---

## 8. Variable Shadowing ב-ImuManager

### האתגר
Refactor של `ImuManager::read()` לשימוש ב-`readRaw()` יצר variable shadowing:
```cpp
int16_t ax, ay, az, gx, gy, gz;  // outer scope
...
float gx = out.gyroX / 131.0f;   // ← shadows int16_t gx!
float gy = ...
```
הקומפיילר של ESP32 לא תמיד מוציא warning על זה.

### הפתרון
שינוי שמות ה-float variables:
```cpp
float fgx = out.gyroX / 131.0f;
float fgy = out.gyroY / 131.0f;
float fgz = out.gyroZ / 131.0f;
```

### הלקח
> בC++ — shadowing לא תמיד שגיאה. הפעל `-Wshadow` כ-build flag בפרויקטי firmware. ב-refactor של פונקציות ארוכות — בדוק ידנית collision של שמות.

---

## 9. mDNS כתחליף ל-ESP-NOW Discovery לOTA

### האתגר
ה-discover הקיים (MSG_DISCOVER → IdentityResponse) נכשל אחרי WiFi connect: Staff על channel אחר → לא מקבל discover → IP לא מגיע למac.

### הפתרון
ArduinoOTA מכריז על `_arduino._tcp` ב-mDNS באופן אוטומטי. גילוי devices:
```bash
dns-sd -B _arduino._tcp local.
# → staff-s3, staff-c3
```

Flash ישירות via hostname — ללא IP:
```bash
pio run -e staff-ota -t upload --upload-port staff-s3.local
```

### הלקח
> ב-WiFi+ESP-NOW coexistence — אל תסמוך על ESP-NOW לגילוי devices שעל WiFi. mDNS זמין בחינם עם ArduinoOTA. השתמש בו.

---

## 10. Hub ESP32 vs ESP32-S3 — Board Mismatch

### האתגר
`platformio.ini` של Hub הכיל `[env:hub]` עם `board = esp32-s3-devkitc-1`, אבל ה-Hub הפיזי הוא ESP32 רגיל. esptool דחה:
```
This chip is ESP32, not ESP32-S3. Wrong --chip argument?
```

### הפתרון
שימוש ב-`[env:hub-esp32]` הקיים (`board = esp32dev`). Hub גם לא נכנס ל-bootloader אוטומטית → לחיצת BOOT ידנית נדרשת.

### הלקח
> תמיד תייג boards בshop labels. ב-monorepo עם מספר envs — הוסף comment על הchip הפיזי שמשויך לכל env. אל תסמוך על ה-default env.

---

## 11. deviceId Collision — שני Staffs עם אותו ID

### האתגר
שני הסטאפים החזירו `deviceId=028C`. נבדק שה-device ID נגזר מ-2 הbytes האחרונים של MAC. ה-C3 עם MAC `10:00:3b:af:02:8c` → `028C`. ה-S3 עם MAC שונה — גם `028C` בחלקו האחרון (צירוף מקרים).

### ההשלכה
Hub לא יכול להבדיל בין שניהם ב-discovery. Telemetry מהשניים מגיע כ"device אחד".

### הלקח
> 2 bytes = 65,536 combinations. לא מספיק לפרויקט עם יותר מכמה מכשירים. **STAFF_ID (NVS)** נוסף כ-mechanism לזיהוי לוגי עצמאי מ-MAC.

---

## 12. wifiDisable() Forward Declaration בלambda

### האתגר
```cpp
static void wifiEnable() {
    ArduinoOTA.onError([](ota_error_t e) {
        wifiDisable();  // ← error: not declared
    });
}
static void wifiDisable() { ... }  // defined after
```
C++ לא מאפשר שימוש בפונקציה לפני הגדרתה, גם בlambdas.

### הפתרון
הזזת `wifiDisable()` **לפני** `wifiEnable()` בקובץ.

### הלקח
> בC++: הסדר בקובץ חשוב. Lambdas לא פותרות forward reference. ב-setup/teardown pairs — תמיד הגדר teardown ראשון.

---

## 13. PlatformIO extra_configs — build_flags לא מתמזגים

### האתגר
`wifi_credentials.ini` עם `[env]` + `build_flags` נטען, אבל הדגלים לא הופיעו בבנייה. `pio project config` הראה אותם, אך `pio run -v` לא.

### הסיבה
`[env:staff]` מגדיר `build_flags` → מחליף את `[env]` global flags. ה-credentials לא מוזגו.

### הפתרון המלא
`build_src_flags` ב-credentials (מצטרף) + `upload_flags` ב-env ספציפי (לא גלובלי).

### הלקח
> בPlatformIO: test credentials בנפרד עם `pio run -v | grep WIFI` לפני שסומכים עליהם בflash.

---

## 14. parallel OTA — Sequential backend שבר את ה-UI

### האתגר
הקוד המקורי ב-Flasher flashed devices אחד אחרי השני. שינוי ל-parallel הצריך refactor של:
- Backend: מtהליך אחד גלובלי (`_proc`) למספר threads
- Frontend: tracking של multiple job completions

### הפתרון
```python
def _spawn_ota(cmd, fw_name, target):
    def run():
        proc = subprocess.Popen(cmd, ...)
        with _ota_lock: _ota_procs[target] = proc
        for raw in proc.stdout:
            socketio.emit('log', {'text': f'[{target}] {raw}', ...})
    threading.Thread(target=run, daemon=True).start()
```
כל OTA job → thread עצמאי → log עם prefix של device.

### הלקח
> parallel OTA חוסך זמן ניכר (60→20 שניות ל-2 devices). תכנן parallel מההתחלה — refactor אחרי זה מסורבל.

---

## 15. env S3 חדש עם flash_size=4MB — partition table ברירת מחדל ל-8MB גרם ל-boot loop

### האתגר
הוספת `env:mic-s3` (ESP32-S3, פלאש 4MB בפועל) ל-`firmware/mic/platformio.ini`, בלי לציין `board_build.partitions`. הבנייה עברה נקי, הצריבה עברה נקי (`esptool` דיווח SUCCESS פעמיים, גם אחרי `erase_flash` מלא) — אבל המכשיר נכנס ל-boot loop אינסופי: ROM bootloader מדפיס `entry 0x403c98d0` וחוזר על עצמו כל ~16ms, לעולם לא מגיע ל-`setup()`.

### הבעיה הספציפית
ברירת המחדל של board definition `esp32-s3-devkitc-1` היא `partitions: default_8MB.csv` — טבלת partitions שבה `app1` מסתיים ב-`0x670000` (6.7MB), הרבה מעבר ל-4MB (`0x400000`) שהוגדרו בפועל דרך `board_build.flash_size = 4MB`. ה-bootloader מזהה טבלת partitions לא תקפה מול גודל הפלאש המוגדר ונכנס ללולאת איפוס.

**אבחון מטעה:** boot loop שקט (בלי panic message, בלי watchdog reason ברור) קל להתבלבל איתו כתקלת USB/דרייבר (macOS native CDC), במיוחד כש-`erase_flash` מלא לא פותר את זה — כי הבעיה היא בקונפיגורציית הבנייה, לא בתוכן ה-flash.

### הפתרון
```ini
[env:mic-s3]
board = esp32-s3-devkitc-1
board_build.flash_size = 4MB
board_build.partitions = min_spiffs.csv   ; ← קריטי: טבלה שמתאימה בפועל ל-4MB
```
`min_spiffs.csv` (app0+app1+spiffs+coredump) מסתיים בדיוק ב-`0x400000` — זהה לדפוס שכבר קיים ב-`firmware/staff/platformio.ini` עבור אותו צירוף (S3 + 4MB).

### הלקח
> כל `env` חדש על ESP32-S3/C3 עם `board_build.flash_size` שאינו ברירת המחדל של ה-board — **חובה** לציין גם `board_build.partitions` מתאים, אחרת ה-bootloader עלול לקבל טבלה שחורגת מהפלאש בפועל. תסמין זה בדיוק כמו לולאת boot "שקטה" — לפני שחושדים ב-USB/דרייבר/חומרה, לבדוק ראשית align בין `flash_size` ל-`partitions`.

---

## סיכום — דפוסים חוזרים

| קטגוריה | לקח מרכזי |
|---------|-----------|
| **ESP-NOW** | Broadcast לא מאשר. Unicast כן. HubAlive = heartbeat mechanism נכון |
| **WiFi+ESP-NOW** | Channel conflict הוא פונדמנטלי. תמיד תכנן recovery path |
| **Protocol** | שינוי struct size = צריבה סינכרונית של כל הרכיבים |
| **PlatformIO** | `build_flags` מחליף, `build_src_flags` מצטרף, `upload_flags` per-env |
| **Testing** | Software-controlled isolation > physical disconnection |
| **Observability** | Announce events מהרגע הראשון — debugging ב-production קשה ללא זה |
| **Firmware** | Board type + chip variant תמיד תייג. WHO_AM_I אל תבדוק exact match |
| **PlatformIO S3/C3** | `flash_size` שהשתנה מברירת המחדל → `board_build.partitions` חובה, אחרת boot loop שקט |

---

*נכתב: 2026-05-31 | Push: a811ee1 → github.com/Russaky/FutureMagzimus*

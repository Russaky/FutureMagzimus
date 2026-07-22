# MAGZIMUS Light Nodes — System Spec

## סקירה כללית

מערכת תאורה מודולרית להופעות חוץ. כל פנס הוא יחידה עצמאית עם בקר משלו. גשר מרכזי מקבל פקודות ממספר מקורות ומממסר ל-nodes באמצעות ESP-NOW.

---

## ארכיטקטורה

```
Serial (מחשב/דיבוג)     ─┐
HTTP (טלפון)             ─┼→ ESP32-S3 גשר → ESP-NOW → C3 Node #1 → PWM → פנס 1
ESP-NOW (מוח)           ─┘                          → C3 Node #2 → PWM → פנס 2
                                                     → C3 Node #3 → PWM → פנס 3
                                                     → C3 Node #4 → PWM → פנס 4

ACK זרימה חזרה:
C3 nodes → ESP-NOW ACK → גשר → Serial בלבד
```

---

## רכיבים

### גשר — ESP32-S3
- מקים WiFi AP (channel 1 קבוע)
- מריץ HTTP server
- מאזין ל-Serial
- מאזין ל-ESP-NOW מהמוח
- ממסר פקודות ל-nodes
- מדפיס ACKs ל-Serial בלבד

### Node — ESP32-C3 (×4)
- מאזין ESP-NOW על channel 1
- מבצע PWM על 4 ערוצים
- שומר סטטוס אחרון בזיכרון
- שולח ACK לגשר על כל שינוי

### חומרה לכל Node
- ESP32-C3 Super Mini
- לוח PWM 4 ערוצים (60N03)
- ממיר מתח 12V→5V (3A)
- פנס RGBW 10W 12V
- ספק כוח 12V

---

## פרוטוקול ESP-NOW

### פקודה (גשר → node)
```c
typedef struct {
  uint8_t target;  // 0=broadcast, 1-4=node ספציפי
  uint8_t r;
  uint8_t g;
  uint8_t b;
  uint8_t w;
} light_cmd_t;    // 5 bytes
```

### ACK (node → גשר)
```c
typedef struct {
  uint8_t node_id;
  uint8_t r;
  uint8_t g;
  uint8_t b;
  uint8_t w;
} light_ack_t;    // 5 bytes
```

### כללים
- fire and forget — אין retry
- broadcast MAC: `{0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF}`
- כל node בודק `target == NODE_ID || target == 0`
- ACK נשלח רק אם הפקודה שונה מהסטטוס הנוכחי

---

## זיהוי Nodes

```c
#define NODE_ID 1  // 1-4, קבוע בקומפיל
```

אין pairing דינמי. אין discovery. ID קבוע.

---

## GPIO — Node C3

```
GPIO 0 → PWM → R
GPIO 1 → PWM → G
GPIO 2 → PWM → B
GPIO 3 → PWM → W
```

- תדר PWM: 1kHz
- API: LEDC (לא analogWrite)
- resolution: 8-bit (0-255)

---

## HTTP API — גשר

```
POST /color
Content-Type: application/json

{
  "target": 0,
  "r": 255,
  "g": 0,
  "b": 0,
  "w": 0
}

Response: {"status":"ok"}
```

- target 0 = כל הnodes
- target 1-4 = node ספציפי
- תגובת HTTP מיידית, לא מחכה ל-ACK

---

## Serial API — גשר

קלט: JSON זהה ל-HTTP, שורה אחת עם `\n`
```
{"target":1,"r":255,"g":0,"b":0,"w":0}\n
```

פלט ACKs:
```
[ACK] Node 1: R=255 G=0 B=0 W=0
[TIMEOUT] Node 3
[BOOT] Bridge ready, channel=1
[BOOT] Node 2 online
```

timeout: 200ms לאחר שליחה

---

## ממשק טלפון

קובץ HTML אחד, מוגש מהגשר על `/`.

**מבנה:**
- שורת "הכל" — target=0
- שורות 1-4 — target ספציפי
- כל שורה: תווית + 4 סליידרים (R/G/B/W) + כפתור SEND
- ללא frameworks, ללא build step

---

## WiFi

### Multi-network boot sequence

The bridge stores two known networks and connects to whichever is available:

```c
// credentials.h — fill in before flashing
const char* networks[][2] = {
  {"HOME_SSID",     "HOME_PASSWORD"},    // home network
  {"HOTSPOT_SSID",  "HOTSPOT_PASSWORD"}, // field smartphone hotspot
};
```

Boot logic:
1. Try network 0 → wait 5 seconds
2. If fail → try network 1 → wait 5 seconds
3. If both fail → fall back to AP mode (SSID: `MagLight`, pass: `magzimus`)
4. On success → apply static IP → print to Serial

### Static IP

Same IP regardless of which network connected:

```c
// config.h
IPAddress static_ip(192, 168, 1, 100);   // adjust to your subnet
IPAddress gateway(192, 168, 1, 1);        // adjust per network
IPAddress subnet(255, 255, 255, 0);
```

**Note:** home network and hotspot may have different gateways. Agent should define both and apply the correct one based on which network connected.

### ESP-NOW channel — פתרון

הגשר עולה תמיד במצב **WIFI_AP_STA** — מתחבר לרשת הידועה כ-STA, ובמקביל מקים AP על **channel 1 קבוע**.

```c
WiFi.mode(WIFI_AP_STA);
WiFi.softAP("MagLight", "magzimus", 1);  // AP על channel 1 — מקבע ESP-NOW
WiFi.begin(ssid, password);              // STA לרשת הביתית/hotspot
```

ה-AP לא חייב לשמש לכלום — תפקידו היחיד הוא לנעול את ה-radio על channel 1 כך שESP-NOW תמיד עובד על channel 1, בלי תלות בראוטר.

כל הnodes מקודדים על channel 1 — פשוט ועובד.

**לשימוש בשטח:** הגדר את ה-hotspot של הסמארטפון על channel 1 (ניתן ב-Android דרך הגדרות מתקדמות של hotspot).

---

## סטטוס אחרון

כל C3 שומר בזיכרון:
```c
uint8_t cur_r, cur_g, cur_b, cur_w = 0;
```
- לא נשמר ב-flash
- אתחול: כולם 0 (כבוי)
- אם מגיעה פקודה זהה לסטטוס — לא עושה כלום, לא שולח ACK

---

## סדר אתחול (קריטי)

### גשר
```c
Serial.begin(115200);
WiFi.mode(WIFI_AP_STA);
WiFi.softAP("MagLight", "magzimus", 1);  // AP על channel 1 — מקבע ESP-NOW
// נסה רשתות בסדר
for (auto& net : networks) {
  WiFi.begin(net[0], net[1]);
  if (WiFi.waitForConnectResult(5000) == WL_CONNECTED) break;
}
if (WiFi.status() == WL_CONNECTED) {
  WiFi.config(static_ip, gateway, subnet);
  Serial.printf("[BOOT] Connected to %s, IP: %s\n",
    WiFi.SSID().c_str(), WiFi.localIP().toString().c_str());
} else {
  Serial.println("[BOOT] No network found, AP mode only");
}
esp_now_init();
// רשום peer broadcast
// הפעל HTTP server
Serial.println("[BOOT] Bridge ready, channel=1");
```

### Node
```c
Serial.begin(115200);
// reset GPIOs מיד
gpio_set_level(GPIO_NUM_0, 0);
gpio_set_level(GPIO_NUM_1, 0);
gpio_set_level(GPIO_NUM_2, 0);
gpio_set_level(GPIO_NUM_3, 0);
// הגדר LEDC
WiFi.mode(WIFI_STA);
esp_wifi_set_channel(1, WIFI_SECOND_CHAN_NONE);  // channel 1 קבוע
esp_now_init();
// רשום callback
```

---

## ESP-NOW Callback — כלל קריטי

```c
// ב-callback — רק שמירה ל-buffer
void on_receive(const uint8_t *mac, const uint8_t *data, int len) {
  memcpy(&pending_cmd, data, sizeof(light_cmd_t));
  has_pending = true;
}

// ב-loop() — ביצוע
void loop() {
  if (has_pending) {
    process_cmd(pending_cmd);
    has_pending = false;
  }
}
```

אסור Serial.print, JSON parsing, או כל פעולה כבדה בתוך callback.

---

## GND משותף

כל הרכיבים חייבים GND משותף:
- גשר
- כל C3
- כל לוח PWM
- ספקי הכוח

בלי GND משותף — ESP-NOW לא עובד באופן אמין.

---

## קבצים

```
bridge/
  └── bridge.ino

node/
  └── node.ino

web/
  └── index.html
```

---

## מה לא כלול (בכוונה)

- אין OTA
- אין authentication
- אין retry על ESP-NOW
- אין שמירת סטטוס ב-flash
- אין discovery דינמי
- אין לוגיקת עדיפות בין מקורות קלט

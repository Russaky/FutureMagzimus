# אפיון מעגל מדידת מתח סוללה עבור בקרי ESP32-C3 / ESP32-S3
(Battery Voltage Monitor Specification for ESP32-C3 and ESP32-S3)

## 1. תקציר מנהלים (Executive Summary)
מסמך זה מפרט את הדרישות החומרתיות והתוכנתיות למימוש מדידת מתח סוללת LiPo/Li-ion חד-תאית (Single-Cell, 3.0V עד 4.2V) במעגלי הבקרה המבוססים על מעבדי ESP32-S3 ו-ESP32-C3 בפרויקט P.o.T Staff. מטרת האפיון היא לייצר מדידה מדויקת ויציבה, למנוע זרמי זליגה (Quiescent Current) בזמן כבוי, ולהימנע מהתנגשויות חומרה בין רכיבי ה-ADC לבין משדר ה-Wi-Fi (ESP-NOW) של הבקר.

---

## 2. אפיון חומרה וסכמה חשמלית (Hardware & Schematic Specification)

### 2.1 סכמה בסיסית (Continuous Monitoring)
מדידת מתח סוללה (עד 4.2V בטעינה מלאה) מחייבת הורדה של המתח מתחת ל-3.3V (מתח העבודה של פיני ה-GPIO בבקר) באמצעות מחלק מתח (Voltage Divider).

```
          VBAT (+3.0V to +4.2V)
                |
               [R1] = 100kΩ (1% Tolerance)
                |
                +-------> ADC1 Pin (e.g., GPIO 1 on S3 / GPIO 0 on C3)
                |       |
               [R2]    [C1] = 100nF (Ceramic Filter)
               100kΩ    |
              (1%)      |
                |       |
               GND     GND
```

* **הסבר הנדסי:** מחלק מתח ביחס של 1:1 ($R_1 = R_2 = 100\text{k}\Omega$) מחלק את המתח ב-2.
  * עבור סוללה טעונה ב-4.2V, המתח בפין ה-ADC יהיה 2.1V.
  * עבור סוללה פרוקה ב-3.0V, המתח בפין ה-ADC יהיה 1.5V.
  * טווח זה מתאים בדיוק לעבודה בתוך טווח הליניאריות המיטבי של ה-ADC של ESP32 עם התנחתה (Attenuation) מוגדרת.

* **זרם זליגה (Quiescent Current Leakage):**
  בסכמה זו קיים נתיב רציף של זרם מהסוללה ל-GND דרך הנגדים.
  $$I_{\text{leak}} = \frac{V_{\text{bat}}}{R_1 + R_2} = \frac{4.2\text{V}}{200\text{k}\Omega} = 21\mu\text{A}$$
  זהו זרם קטן מאוד שאינו משפיע בזמן עבודה אקטיבית, אך עלול לרוקן סוללה המאוחסנת לאורך מספר חודשים.

### 2.2 סכמה מתקדמת למניעת זליגה (Active Load Switch)
כדי לאפס לחלוטין את זרם הזליגה כאשר הבקר כבוי או בשינה עמוקה, ניתן לשלב טרנזיסטור מסוג P-channel MOSFET (כגון DMG2305 או דומה) וטרנזיסטור NPN/N-MOSFET כמתג:

```
          VBAT (+3.0V to +4.2V)
                |
            [S] |
           +----+  Q1 (P-Channel MOSFET, DMG2305)
           |    \ [D]
      [R3] |     +-------------+
      10kΩ |    /              |
           +---|               [R1] = 100kΩ (1%)
           |   [G]             |
           |                   +-------> ADC1 Pin
           +--[R4]--+          |       |
              10kΩ  |         [R2]    [C1] = 100nF
                    |         100kΩ    |
                    |         (1%)     |
                  [C]          |       |
                 +---+         +-------+
            B1   |   | Q2      |
     GPIO ---> [B]   | (NPN,   |
   (CTRL)        |   | MMBT3904)
                 +---+         |
                  [E]          |
                    |          |
                   GND        GND
```

* **אופן הפעולה:**
  * כאשר פין ה-GPIO CTRL נמצא ב-`LOW` (או במצב High-Impedance בזמן שינה/כיבוי), הטרנזיסטור Q2 סגור, שער המוספט Q1 נמשך ל-VBAT דרך $R_3$, ולכן Q1 סגור ואין זליגת זרם דרך מחלק המתח.
  * כדי לבצע מדידה, הבקר מעלה את פין ה-GPIO CTRL ל-`HIGH` (3.3V). Q2 נפתח, מושך את שער המוספט Q1 ל-GND, המוספט Q1 נפתח ומאפשר זרם למחלק המתח. המדידה מתבצעת, ולאחר מכן הפין CTRL מוחזר ל-`LOW`.

---

## 3. דרישות חלוקת פינים ומניעת התנגשויות (Pinout & Hardware Constraints)

> [!IMPORTANT]
> **שימוש בפיני ADC1 בלבד!**
> מעבדי ESP32 משתמשים בבקר ה-ADC2 לניהול משדר ה-Wi-Fi. ביצוע קריאות ADC מפינים השייכים ל-ADC2 בזמן עבודת Wi-Fi/ESP-NOW ייכשל, יגרום לשגיאות בקוד או יחזיר קריאות לא יציבות.

* **ESP32-S3 ADC1 Pins:** GPIO 1, 2, 3, 4, 5, 6, 7, 8, 9, 10.
* **ESP32-C3 ADC1 Pins:** GPIO 0, 1, 2, 3, 4.

יש להקצות את פין המדידה (ומתג השליטה, אם מיושם) אך ורק מתוך הפינים השייכים ל-**ADC1**.

---

## 4. ארכיטקטורת תוכנה וקושחה (Software & Firmware Specification)

### 4.1 כיול ה-ADC באמצעות ה-eFuse
ממירי ה-ADC ב-ESP32 ידועים באי-ליניאריות מסוימת. עם זאת, רכיבי ESP32-S3 ו-ESP32-C3 מכילים נתוני כיול אינדיבידואליים שנצרבו במפעל ב-eFuse.
בסביבת Arduino ESP32 Core, ספריית ה-HAL מספקת פונקציה מובנית הממירה את הקריאה הגולמית (Raw ADC 0-4095) ישירות למתח מדויק במילי-וולטים על בסיס נתוני ה-eFuse:

```cpp
#define BATTERY_ADC_PIN   1   // ADC1 Pin (Change to actual pin used)
#define DIVIDER_RATIO     2.0f

float readBatteryVoltage() {
    // analogReadMilliVolts handles the calibration automatically using eFuse values
    uint32_t pin_mv = analogReadMilliVolts(BATTERY_ADC_PIN);
    
    // Convert pin voltage back to battery voltage
    float vbat = (pin_mv * DIVIDER_RATIO) / 1000.0f;
    return vbat;
}
```

### 4.2 מניעת השהיות (Latency Mitigation)
* **הבעיה:** קריאת ADC בודדת לוקחת כ-10-20 מיקרו-שניות. ביצוע ריבוי דגימות (Over-sampling) לצורך סינון רעשים בלופ הראשי של התוכנה עלול לפגוע בקצב רינדור הלדים (FastLED) ולפגוע בביצועי תקשורת ה-ESP-NOW.
* **הפתרון:** ביצוע קריאה אסינכרונית לא-חוסמת (Non-blocking Timer) כל 5 שניות, מבוססת `millis()`:

```cpp
void updateBatteryTelemetry() {
    static uint32_t lastCheck = 0;
    if (millis() - lastCheck >= 5000) { // Check battery every 5000ms
        lastCheck = millis();
        
        float raw_v = readBatteryVoltage();
        // Send raw_v to filter
    }
}
```

### 4.3 סינון רעשים וצידוד (Voltage Sag Filtering)
* **הבעיה:** פסי הלדים WS2812B מייצרים שינויי זרם חדים ומהירים (Inrush/Current Spikes) בזמן הפעלת אפקטים. עקב התנגדות פנימית של הסוללה (Internal Resistance), נוצרים נפילות מתח רגעיות (Voltage Sag) שאינן מייצגות את רמת הטעינה האמיתית של הסוללה.
* **הפתרון:** החלקת הקריאות על ידי מסנן ממוצע נע אקספוננציאלי (Exponential Moving Average - EMA) בקושחה:
  $$V_{\text{filtered}} = \alpha \cdot V_{\text{new}} + (1 - \alpha) \cdot V_{\text{filtered}}$$
  עבור $\alpha = 0.05$, המערכת תסנן רעשים מהירים ותציג מגמה ארוכת טווח של מצב הסוללה.

### 4.4 ניהול מצבי סוללה והגנה מפריקת יתר (Under-Voltage Protection)
* סוללות ליתיום נפגעות לצמיתות אם הן נפרקות מתחת ל-3.0V.
* **מדיניות קושחה:**
  * **$V_{\text{bat}} > 3.6\text{V}$**: עבודה רגילה.
  * **$3.6\text{V} \ge V_{\text{bat}} > 3.3\text{V}$**: אזהרת סוללה חלשה (שליחת דגל telemetry מתאים ל-Hub, ואולי חיווי ויזואלי של הלדים).
  * **$V_{\text{bat}} \le 3.2\text{V}$**: מצב חירום. הבקר יכבה את כל נורות הלד, יכבה את משדר ה-Wi-Fi, ויכנס לשינה עמוקה (Deep Sleep) כדי להגן על הסוללה מפריקה מלאה.

---
*סוף מסמך אפיון.*

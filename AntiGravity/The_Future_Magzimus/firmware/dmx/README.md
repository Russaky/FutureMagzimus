# DMX512 Output — ESP32-S3 SuperMini + MAX485

תיקייה ייעודית לפיתוח שידור DMX512 מה-ESP32-S3 SuperMini דרך MAX485.
לא חלק מארכיטקטורת ESP-NOW הקיימת (ראה `CLAUDE.md` בשורש) — מדובר בפיצ'ר עצמאי בשלב בדיקת חומרה (bring-up), עדיין לא משולב במערכת הנאמברים/Nodes.

## סטטוס: בבדיקת חומרה — קוד כתוב, טרם אומת שידור מלא

---

## חומרה

| רכיב | פרט |
|------|-----|
| בקר | ESP32-S3 SuperMini |
| שבב שידור | MAX485 (RS-485 transceiver) |
| מתח MAX485 | VCC 5V, GND משותף ל-ESP32 |
| TX (DI) | GPIO2 (פין D2 פיזית על הלוח) |
| EN (RE+DE מחוברים יחד) | GPIO1 (פין PIO1 פיזית על הלוח) |
| RX | לא בשימוש (אין קליטת DMX בפרויקט) |
| DMX Port בספרייה | `DMX_NUM_2` |
| ספרייה | `esp_dmx` by someweisguy (Arduino Library Manager) |

### עקרון חיווט
EN (RE+DE) נשלט **ידנית** ב-firmware (`pinMode`/`digitalWrite`) ולא דרך `dmx_set_pin()` של הספרייה — כדי להבטיח שה-MAX485 נשאר במצב Driver Enable (שידור) קבוע, ללא toggle אוטומטי של הספרייה בין TX/RX.

---

## קבצים

```
firmware/dmx/
├── README.md              # מסמך זה
├── platformio.ini         # הגדרות פרויקט PlatformIO
└── src/
    └── main.cpp           # קוד בדיקת שידור בסיסית
```

`main.cpp` — שולח פריים DMX512 מלא (512 ערוצים) ברצף, ~40Hz (כל 25ms).
תבנית טסט: ערוץ 1 = 255, כל שאר הערוצים = 0.

---

## לוג אימות (multimeter, ללא אוסילוסקופ)

| בדיקה | תוצאה |
|-------|-------|
| VCC↔GND על MAX485 | ✅ תקין (~5V) |
| EN (RE+DE)↔GND | ✅ תקין (מתח יציב על 2.36V/GND) |
| A↔GND, B↔GND, A↔B (שידור בפועל) | ✅ תקין (הפרש מתחים תקין ותנודות שידור) |
| Flash + Serial Monitor (אימות שה-firmware רץ בפועל) | ✅ תקין (נצרב בהצלחה דרך PlatformIO, לופ האתחול נפתר) |
| בדיקת פיקסצ'ר DMX (פנס בכתובת 1) | ✅ תקין (הפנס מגיב במדויק לערוצים 1-10 המשודרים כ-255) |

---

## שלבים הבאים

1. **Flash** את הקוד דרך PlatformIO:
   ```bash
   pio run -t upload -d firmware/dmx
   ```
2. **Serial Monitor** ב-115200 baud:
   ```bash
   pio device monitor -d firmware/dmx
   ```
   לוודא שמופיעה ההודעה `DMX TX test (PlatformIO) — channel 1 = 255, running @ ~40Hz`.
3. **מולטימטר**: A↔GND, B↔GND, A↔B — לוודא תנודות (לא ערך קפוא) בזמן שידור. פירוט מלא בהיסטוריית הבדיקות של הצ'אט / DONE.md כשיתווסף.
4. **אוסילוסקופ** (אם זמין): לאמת break (~92µs+), MAB (~12µs), ותדר frame ~40Hz.
5. **DMX tester / פיקסצ'ר DMX ידוע** בכתובת 1: לוודא תגובה יציבה ללא flicker.
6. רק לאחר אימות מלא — אינטגרציה עם מערכת הנאמברים (מחוץ לסקופ הנוכחי).

## הערות לסוכן (המשך עבודה)
- `DMX_ENABLE_PIN` מחובר ל-GPIO1 (פין PIO1) ו-`TX_PIN` מחובר ל-GPIO2 (פין D2).
- זהו פרויקט PlatformIO תקני.
- כשהאימות המלא (multimeter + Serial + פיקסצ'ר) יושלם, לתעד בטבלת "לוג אימות" למעלה ולשקול הוספת ערך ל-`docs/agent/DONE.md` לפי הפורמט הקבוע בפרויקט.

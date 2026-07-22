# MAGZIMUS OS — Node Editor Specification
## גרסה 2.0 | מסמך אפיון מלא

---

## 1. סקירת המערכת

### ארכיטקטורה כללית

```
MacBook (Node Editor — Flask Web App)
    ↓ USB Serial
ESP32 Brain (מנהל רשת)
    ↓ ESP-NOW
מכשירים (Staff, Lights, Progress Bar, Smoke, Microphone, Pedal)
```

ה-Node Editor הוא web app שרץ לוקלית על MacBook דרך Flask. המשתמש בונה לוגיקת הופעה ויזואלית בקנבס, מאמת, ודוחף את הקנבס ל-Brain דרך USB Serial. ה-Brain מנהל את הרשת ומתקשר עם המכשירים דרך ESP-NOW.

---

## 2. מכשירים (Device Registry)

### 2.1 רשימת מכשירים

| מכשיר | סוג | חומרה | תפקיד |
|---|---|---|---|
| Staff | input + output | ESP32-S3 + MPU6500 + 2× WS2812B matrix | ג'אגלינג — סנסור + תאורה |
| Lights | output | ESP32-C3 + 4× 10W WRGB | פנסי במה |
| Progress Bar | output | ESP32-C3 + 100× WS2812B | פס LED לקהל |
| Smoke Relay | output | ESP32-C3 + relay | מכונת עשן |
| Microphone | input | ESP32-C3 + MAX9814 | סנסור קהל |
| Pedal | input | ESP32 + microswitch | שליטה ידנית |

### 2.2 פירוט מכשירים

**Staff**
- שני ראשים (master/slave) — נשלטים כמכשיר אחד בקנבס
- כל ראש: מטריקס 5×26 WS2812B (130 LEDs לראש, 260 סה"כ)
- Master משדר טלמטריה ל-Brain
- סנסורי IMU: angle, velocity, acceleration, throw/catch
- throw/catch מזוהה על ESP32 firmware ומדווח כevent בינארי
- אפקטים: נטענים דינמית לפי firmware

```
⚠ OPEN QUESTION — למפתח:
Staff — שני ראשים (master/slave). Master משדר טלמטריה.
נדרש הסבר על פרוטוקול תקשורת בין הראשים ובין Master ל-Brain.
לוודא תאימות עם אפיון הקנבס — האם הממשק רואה Staff כמכשיר אחד או שניים.
```

**Lights**
- 4 פנסים זהים, נשלטים כmכשיר אחד (gang)
- פקודה אחת הולכת לכולם במקביל
- פרמטרים: color (WRGB), brightness
- תומך ב-IDLE state

**Progress Bar**
- 100 LEDs addressable
- שימוש כפול: progress bar לקהל + גוף תאורה כללי
- תומך ב-IDLE state

**Smoke Relay**
- בינארי: on/off
- פרמטר נוסף: duration (משך ה-on במילישניות)

**Microphone**
- RMS ו-peak מחושבים על ESP32 firmware (לא נתונים גולמיים)
- מדווח ל-Brain כערכים מעובדים

```
⚠ OPEN QUESTION — למפתח:
RMS ו-peak מחושבים על ESP32 firmware.
נדרש תיעוד על window size, sample rate, וספי זיהוי
לוודא תאימות עם פרמטרי TRIGGER.
```

**Pedal**
- שלושה events בסיסיים + timing events מורכבים — כולם מזוהים על firmware
- מכשיר input לכל דבר — יושב בספריית הסנסורים
- נורת LED מובנית: ירוק = רשת תקינה, צהוב = מכשיר חסר, אדום = Brain לא מחובר

### 2.3 Device Registry — הגדרה אופליין

המשתמש מגדיר מכשירים ידנית (שם, סוג, מזהה) כדי שניתן לבנות קנבס לפני שהמכשיר מחובר פיזית.

**שני מצבי מכשיר:**

| מצב | משמעות | ויזואלי בקנבס | VALIDATE |
|---|---|---|---|
| `planned` | מוגדר באפיון, לא קיים פיזית | אייקון שונה, opacity עדין | אזהרה בלבד |
| `active` | מחובר לרשת ומזוהה | רגיל | מלא |

מכשיר planned מאפשר בניית לוגיקה מלאה בקנבס. כשהמכשיר מתחבר פיזית — המפתח מקשר את ה-ID ומצב planned הופך active אוטומטית.

```
⚠ OPEN QUESTION — למפתח:
קושחה למכשירים planned טרם קיימת.
האפיון מגדיר את ה-interface — הקושחה תפותח בנפרד.
```

```
⚠ OPEN QUESTION — למפתח:
מנגנון זיהוי מכשיר בחיבור לרשת — יש פרוטוקול קיים, צריך תיעוד.
לוודא שהמכשיר מזדהה אוטומטית ל-Registry לפי המזהה הקיים.
```

### 2.4 אפקטים על LED

רשימת האפקטים הזמינים לכל מכשיר LED **נטענת דינמית** מה-Brain לפי מה שה-firmware של כל מכשיר מדווח שהוא תומך בו. הממשק לא מכיל רשימה סטטית.

```
⚠ OPEN QUESTION — למפתח:
האם פסי LED רצים על WLED או firmware מותאם?
אם WLED — Brain מתקשר דרך JSON API והאפקטים נטענים אוטומטית.
אם firmware מותאם — צריך להגדיר פרוטוקול אפקטים ידנית.
ההכרעה משפיעה על כל ממשק עריכת האפקטים.
```

---

## 3. מבנה הממשק

### 3.1 שלושה אזורים

**Sidebar** — ספריית נודים מחולקת לקטגוריות. גרירה לקנבס מוסיפה נוד.

**Canvas** — הקנבס הראשי. זרימה שמאל לימין. פאן וזום חופשי.

**Side Panel** — נפתח בלחיצה על נוד. מציג פרמטרים עם כפתורים וסליידרים.

### 3.2 קטגוריות הסיידבר

| קטגוריה | נודים |
|---|---|
| Sensors | Staff, Microphone, Pedal |
| Logic | TRIGGER, COMBINE |
| Control | SHOW TIMER, ACCUMULATOR |
| Actions | EVENT, SEQUENCE, IDLE |

---

## 4. נודים — מפרט מלא

### 4.1 SENSOR

מייצג מכשיר input ברשת. מחובר לTRIGGER משמאל.

**Staff** — פלטי סנסור:
- `angle` — זווית נוכחית
- `velocity` — מהירות סיבוב
- `acceleration` — תאוצה
- `throw` — event בינארי (זוהה ב-firmware)
- `catch` — event בינארי (זוהה ב-firmware)
- `spin_direction` — כיוון סיבוב: CW / CCW (זוהה ב-firmware)
- `orientation` — מצב: vertical / horizontal / inverted (זוהה ב-firmware)
- `impact` — event בינארי: זיהוי הלם (זוהה ב-firmware)

**Microphone** — פלטי סנסור:
- `rms` — עוצמה ממוצעת
- `peak` — פסגת עוצמה
- `frequency` — טון דומיננטי (Hz, זוהה ב-firmware)

**Pedal** — פלטי סנסור:
- `press` — event בינארי
- `release` — event בינארי
- `hold` — event רציף
- `short` — press+release מתחת לthreshold (זוהה ב-firmware)
- `long` — press מעל threshold (זוהה ב-firmware)
- `double` — שני press בתוך time_window (זוהה ב-firmware)
- `triple` — שלושה press בתוך time_window (זוהה ב-firmware)

```
⚠ OPEN QUESTION — למפתח:
Pedal firmware — threshold ו-time_window לזיהוי short/long/double/triple.
האם הערכים קבועים או ניתנים לכוונון מהממשק?
```

כל סנסור יכול להיות מחובר לכמה TRIGGERים במקביל.

**תיוג per-device:** כל פלט סנסור מתויג `device_id.signal` (למשל `staff_01.velocity`, `mic_01.rms`). מאפשר הפעלת מספר מכשירים מאותו סוג במקביל.

---

### 4.2 TRIGGER

מגדיר תנאי המרה מערך גולמי לסיגנל. מתחבר לSENSOR משמאל ולaction מימין.

**Side Panel:**
```
type:      [range] [threshold]
value/min/max:  סליידר
debounce:  סליידר (ms)
cooldown:  סליידר (ms)
priority:  1–5 (ברירת מחדל: 3) — קובע עדיפות כשמכשיר מקבל פקודות ממקורות מרובים
[TEST]     שליחת סיגנל מדומה
```

**TEST:** אם המכשיר מחובר — מפעיל בלייב. אם מנותק — מדמה בממשק בלבד.

**חיבור חוקי:** TRIGGER מתחבר לSENSOR בלבד — לא לCOMBINE ולא לנודים אחרים.

**OR לוגיקה:** מיושמת על ידי חיבור כמה TRIGGERים במקביל לאותו action — אין נוד OR.

---

### 4.3 COMBINE

מאחד כמה TRIGGERים לתנאי AND אחד.

**זרימה:**
```
SENSOR → TRIGGER → ┐
                   COMBINE (AND) → ACTION
SENSOR → TRIGGER → ┘
```

**קלט:** TRIGGERים בלבד (לא סנסורים ישירות).
**לוגיקה:** switch — high כל עוד כל התנאים מתקיימים, low כשאחד נשבר.

**Side Panel:**
```
logic:       AND (בלבד)
time_window: סליידר (ms) — חלון שבתוכו כל התנאים חייבים להתקיים
```

---

### 4.4 EVENT

פעולה חד פעמית — מופעל מטריגר, רץ ונגמר. מיועד לאלתור וגמישות בזמן אמת, ללא timeline.

**סוגי events:**
- `flash` — הבהוב LED
- `smoke_burst` — פרץ עשן עם duration

**Side Panel:** פרמטרים לפי סוג הevent הנבחר.

---

### 4.5 SEQUENCE

רצף מתוזמן עם timeline פנימי. מופיע כנוד מכווץ, לחיצה מרחיבה inline בקנבס.

**פורטים:**
```
start       ◀ מתחיל את הסקוונס
stop        ◀ עוצר את הסקוונס
done        ▶ יוצא כשהסקוונס הסתיים
interrupted ▶ יוצא אם נעצר באמצע
```

#### Timeline

כל מכשיר שמוסיפים לסקוונס יוצר **track**. בלוקים על הtrack הם פקודות למכשיר.

**כללים:**
- בלוקים לא יכולים להתחפף על אותו track
- בסוף בלוק — המכשיר נכבה (שחור / off)
- fade_out: סליידר (ms) per-block — ברירת מחדל 0 (כיבוי מיידי)
- רציפות = gap=0 בין בלוקים
- אורך בלוק חופשי כל עוד לא עובר את אורך הסקוונס

**שלושה סוגי בלוקים:**

**STATIC** — ערך קבוע. צבע, עוצמה, פרמטר מוגדר מראש.

**REACTIVE** — המכשיר עוקב אחרי סנסור בזמן אמת. המשתמש בוחר סנסור מהמכשירים הקיימים ברשת ומגדיר mapping לפרמטר היעד.

**EFFECT** — אפקט עצמאי עם לוגיקה firmware. רשימה נטענת דינמית לפי מה שהמכשיר תומך.
פרמטרים: מהירות, צבע, עוצמה (לפי האפקט).

**אינטראקציות בלוק:**
- לחיצה → side panel
- גרירה → שינוי מיקום
- גרירת קצה ימני → שינוי אורך
- קליק ימין → duplicate / delete

---

### 4.6 SHOW TIMER

נוד ניהול נאמבר. קטגוריה: Control.

**תפקיד:** מופעל על ידי טריגר (בדרך כלל Pedal), עוצר את כל הסקוונסים והאפקטים הפעילים, מאפס את המערכת למצב ידוע, ומתחיל את הלוגיקה הראשונה. סופר זמן ויורה סיגנל בסוף — גיבוי לקליימקס או שמירה על לו"ז.

**פורטים:**
```
start  ◀ מפעיל
done   ▶ יוצא כשהזמן נגמר
```

**Side Panel:**
```
duration:       סליידר (שניות)
on_start:       [reset all] [keep active]
```

**הרשאת system-level:** מוצהרת מפורשות בside panel — SHOW TIMER עוצר את כל הפעולות הפעילות בהפעלה. כל המכשירים חוזרים למצב ה-IDLE המוגדר שלהם (או כבויים אם אין IDLE מוגדר).

---

### 4.7 ACCUMULATOR

נוד ניקוד קהל. קטגוריה: Control.

**תפקיד:** צובר פולסים מTRIGGERים, מנהל progress bar, ויורה events כשמגיע לסף.

**פורטים:**
```
[input]  ◀ מקבל פולסים מTRIGGERים
value    ▶ 0–100% רציף — לחיבור ישיר ל-Progress Bar
scored   ▶ פולס על כל ניקוד — לתגובה מיידית (פנס, flash)
climax   ▶ פולס כש-100% — מפעיל קליימקס
```

**Side Panel:**
```
threshold:  כמה פולסים = 100%
reset:      [auto reset after climax] [manual]
```

**איפוס אוטומטי בסיום נאמבר:** כאשר SHOW TIMER יורה `done` — ACCUMULATOR מתאפס אוטומטית ללא תלות בהגדרת reset.

```
decay:      [off] [slow] [medium] [fast]
decay_rate: סליידר (% לשנייה) — מופיע רק כש-decay פעיל
```

**decay:** ברירת מחדל off — הפרוגרס לא יורד. אפשרות הפעלה לצורך דרמטורגי של "סכנה" ומתח.

**ויזואלי בקנבס:** הנוד מציג progress bar חי בזמן הופעה.

---

### 4.8 IDLE

מגדיר את מצב ברירת המחדל של מכשיר כשאין טריגר פעיל.

**רלוונטי ל:** Lights, Progress Bar בלבד.

**התנהגות ברירת מחדל (ללא IDLE נוד):** מכשיר כבוי.

**IDLE בזמן SEQUENCE:** מצב IDLE נכנס לתוקף רק כשה-SEQUENCE נגמר לחלוטין — לא בין בלוקים.

**Side Panel:** פרמטרי מכשיר היעד (צבע, עוצמה וכו׳).

---

## 5. כללי חיבור וValidation

### 5.1 כללי חיבור חוקיים

```
SENSOR      → TRIGGER
TRIGGER     → COMBINE
TRIGGER     → EVENT
TRIGGER     → SEQUENCE (start/stop)
TRIGGER     → SHOW TIMER (start)
TRIGGER     → ACCUMULATOR
COMBINE     → EVENT
COMBINE     → SEQUENCE (start/stop)
COMBINE     → ACCUMULATOR
ACCUMULATOR → output device (value port)
```

### 5.2 כללי אי-חיבור

- SENSOR לא מתחבר ישירות לCOMBINE — חייב לעבור דרך TRIGGER
- מכשיר output מקבל פקודות ממקור אחד בלבד בכל זמן נתון
- שני SEQUENCEים שיכולים לרוץ במקביל לא יכולים לשלוט באותו מכשיר

### 5.3 Validation — שגיאות חוסמות OTA

- מכשיר output עם יותר ממקור פקודה אחד
- שני מקורות עם priority שווה על אותו מכשיר
- SENSOR מחובר ישירות לCOMBINE
- וויירים לא חוקיים (סוגים לא תואמים)

### 5.4 Validation — אזהרות (לא חוסמות)

- וויירים מחוברים לפורט לא מוגדר — מסומנים ⚠ בצהוב

**OTA UPLOAD חסום** עד שכל השגיאות החוסמות נפתרות. אזהרות לא חוסמות OTA.

---

## 6. פרמטרים גלובליים

### 6.1 AUDIENCE_WINDOW_MS

חלון זמן לתגובת קהל. ברירת מחדל גלובלית עם אפשרות דריסה per-TRIGGER.

```
גלובלי (ברירת מחדל):
  AUDIENCE_WINDOW_MS: 500ms

דריסה מקומית על TRIGGER ספציפי:
  gesture "false_cue":
    AUDIENCE_WINDOW_MS: 200ms
```

הTRIGGER בודק קודם אם יש לו ערך מקומי — אם לא, נופל לגלובלי.

### 6.2 CLIMAX_THRESHOLD

עבר ל-ACCUMULATOR כפרמטר `threshold` — אינו פרמטר גלובלי.

---

## 7. אינטראקציות קנבס

### 7.1 הוספת נוד

- גרירה מסיידבר
- טולבר עם כל הקטגוריות
- קליק ימין על קנבס — מציג נודים תכופים per-file לפי שימוש

### 7.2 עריכה

- לחיצה על נוד → side panel
- לחיצה כפולה על שם → rename inline
- DELETE / קליק ימין → מחיקה

### 7.3 Undo/Redo

Cmd+Z / Cmd+Y — היסטוריה של 50 פעולות.

### 7.4 שמירה

- אוטומטית לקובץ לוקלי עם debounce
- כפתור SAVE בטולבר לשמירה מפורשת

### 7.5 OTA Upload

- כפתור VALIDATE — מציג רשימת שגיאות ואזהרות
- כפתור OTA UPLOAD — חסום עד validation נקי
- דוחף את כל הקנבס כולו בכל פעם (לא diff)
- תקשורת דרך USB Serial ל-Brain

```
⚠ OPEN QUESTION — למפתח:
פרוטוקול תקשורת בין MacBook ל-Brain דרך USB Serial —
נדרש תיעוד על baud rate, פורמט הודעות, וhandshake לוודא תאימות עם OTA UPLOAD.
```

### 7.6 Snapshots

- נשמר אוטומטית לפני כל OTA UPLOAD
- 10 snapshots אחרונים עם timestamp
- כפתור REVERT בטולבר — מציג רשימה לבחירה ושחזור

---

## 8. Resilience — התמודדות עם כשלים

### 8.1 מכשיר שנופל מהרשת

- המערכת ממשיכה לפעול — graceful degradation
- המכשיר החסר פשוט שותק (לא מבצע פקודות)
- אם Staff נופל: הטריגרים המבוססים עליו לא יורים, Staff ממשיך לפעול standalone לפי תכנית גיבוי מובנית ב-firmware
- נורת LED על Pedal מסמנת מצב רשת בזמן אמת

---

## 9. Gestures

כל gesture הוא קובץ JSON שנוצר מהקנבס. הוספת gesture = בניית רצף נודים חדש ושמירה. אין צורך לגעת בקוד.

---

## 10. שפה עיצובית (Design Language)

### 10.1 עקרונות

- **Light Mode** — רקע קרם חמים, טקסט כהה. ללא dark mode.
- **קריאות ראשית** — קונטרסט נוח לעיניים, ללא טקסט בהיר על רקע כהה.
- **עברית + אנגלית מעורבת** — ממשק דו-לשוני, RTL.

### 10.2 פונטים

| שימוש | פונט |
|---|---|
| טקסט UI, תוויות, כותרות | Alef (עברי/לטיני) |
| ערכים טכניים, פרמטרים, קוד | IBM Plex Mono |

### 10.3 Color Tokens

| Token | ערך | שימוש סמנטי |
|---|---|---|
| `--bg-base` | `#F5F4F0` | רקע כללי, Canvas |
| `--bg-surface` | `#FFFFFF` | כרטיסים, נודים, פאנלים |
| `--bg-elevated` | `#EEECEA` | שדות קלט, tracks |
| `--orange` | `#C46E00` | פעולות ראשיות, TRIGGER, OTA |
| `--orange-light` | `#FFF0DC` | רקע כתום עדין |
| `--orange-border` | `#E8B070` | גבולות כתום |
| `--orange-text` | `#7A4400` | טקסט על רקע כתום בהיר |
| `--purple` | `#5B2BA8` | SENSOR — input |
| `--purple-light` | `#F0EBFF` | רקע סגול עדין |
| `--purple-border` | `#B099E0` | גבולות סגול |
| `--purple-text` | `#3A1A70` | טקסט על רקע סגול בהיר |
| `--green` | `#1A7A40` | validation תקין, output |
| `--green-light` | `#E8FFF1` | רקע ירוק עדין |
| `--green-border` | `#7ACCA0` | גבולות ירוק |
| `--green-text` | `#0D4F28` | טקסט על רקע ירוק בהיר |
| `--error` | `#C0392B` | שגיאות חוסמות |
| `--ink-900` | `#1A1814` | טקסט ראשי |
| `--ink-500` | `#6A6860` | תוויות משניות |
| `--border` | `#DDDBD5` | גבולות רגילים |
| `--border-strong` | `#C8C6C0` | גבולות מודגשים |

### 10.4 צבעים סמנטיים לנודים

| קטגוריה | צבע (border-top) | משמעות |
|---|---|---|
| SENSOR | `--purple` | input — מה שנמדד |
| TRIGGER / COMBINE | `--orange` | לוגיקה — תנאים |
| SEQUENCE / EVENT | `--green` | output — מה שקורה |
| CONTROL | `--ink-300` | ניהול מערכת |

### 10.5 Spacing & Radius

```
radius-sm:  4px  — כפתורים, שדות
radius-md:  6px  — רכיבים בינוניים
radius-lg:  10px — כרטיסים, נודים, פאנלים

padding נוד:     12px 14px
padding פאנל:    20px
padding toolbar: 8px 12px
gap בין נודים:   12px
```

### 10.6 קובץ סקיצה

`magzimus_ui_sketch.html` — קובץ HTML אינטראקטיבי המדגים את השפה העיצובית המלאה.
כולל: color tokens, toolbar, nodes על canvas, side panel, timeline, validation states, pedal status LED.

---

## 10.7 Tooltips, Modals, Toasts, Context Menus

### Tooltips

**Hover על פורט:**
- שם הפורט
- ערכים נוכחיים של הפרמטרים

**Hover על נוד:**
- שם הנוד
- כל הפרמטרים הנוכחיים
- שגיאות validation אם קיימות (מסומנות באדום)

---

### Modals

**REVERT לSnapshot:**
- נפתח בלחיצה על REVERT בטולבר
- מציג רשימת 10 snapshots עם timestamp
- דורש בחירה + אישור מפורש לפני דריסת הקנבס

**מחיקת SEQUENCE עם תוכן:**
- נפתח אוטומטית כשמוחקים SEQUENCE שיש בו בלוקים
- דורש אישור בלבד (כן/לא)
- SEQUENCE ריק נמחק ישירות ללא modal

---

### Toasts

מוצגים בתחתית המסך, נעלמים אוטומטית:

| מצב | צבע | טקסט |
|---|---|---|
| OTA התחיל | ניוטרלי | שולח לBrain... |
| OTA הצליח | ירוק | הקנבס נטען בהצלחה |
| OTA נכשל | אדום | שגיאה בחיבור — נסה שוב |

---

### Context Menus

**קליק ימין על קנבס:**
- נודים תכופים לפי שימוש (per-file)

**קליק ימין על נוד:**
- Duplicate
- הקפא / בטל הקפאה
- Delete

**קליק ימין על ויר:**
- Delete

---

### מצב מוקפא (Frozen Node)

- הנוד נשאר בקנבס אך המערכת מתעלמת ממנו לחלוטין
- ויזואלית: opacity נמוך על הנוד וכל הוויירים שלו
- שימושי לדיבוג — בדיקת התנהגות הקנבס ללא נוד ספציפי
- VALIDATE מתעלם מנוד מוקפא (לא מדווח שגיאות עליו)

## 12. קומפילר — עקרונות ופיתוח

### 12.1 עקרון מרכזי

הקושחה של Brain היא **runtime engine סטטי** — כתובה פעם אחת, מריצה כל קנבס.
ה-OTA דוחף **data בלבד** (JSON minified) — לא קוד.
שינוי gesture = שינוי data. אין צורך לגעת בקושחה.

---

### 12.2 תפקיד הקומפילר

הקומפילר הוא שכבת תרגום בין הקנבס הויזואלי לבין ה-JSON שה-Brain מבין.

```
קנבס (graph של נודים וחיבורים)
    ↓ VALIDATE
    ↓ COMPILE
JSON minified payload
    ↓ USB Serial
Brain (parse חד פעמי → זיכרון)
```

---

### 12.3 עקרונות הקומפילר

**1. Validate לפני הכל**
הקומפילר לא רץ על קנבס לא תקין. VALIDATE הוא שלב מחייב ואוטומטי לפני כל compilation.

**2. טופולוגיה מסודרת**
הפלט מאורגן לפי שכבות — sensors לפני triggers לפני actions. מבטיח ש-Brain יכול לבנות את ה-dependency graph בסדר נכון בפעם אחת.

**3. Frozen nodes נכללים עם flag**
נוד מוקפא לא מושמט — נשלח עם `"frozen": true`. Brain מתעלם ממנו בריצה אך שומר אותו לשחרור עתידי ללא OTA.

**4. Minified תמיד**
פלט ייצור הוא minified JSON. human-readable זמין רק כ-debug flag בזמן פיתוח.

**5. Payload limit**
גודל מקסימלי: 64KB. חריגה = שגיאה חוסמת ב-VALIDATE.

**6. Persistent על Brain**
Brain שומר את הpayload האחרון בflash. נפילת חשמל = boot מהקנבס האחרון ללא OTA מחדש.

**7. Data-driven בלבד**
הקומפילר לא מייצר קוד — רק data. כל לוגיקת הריצה יושבת בקושחה.

---

### 12.4 מבנה ה-Payload

```json
{
  "version": "2.4",
  "globals": { ... },
  "devices": [ ... ],
  "sensors": [ ... ],
  "triggers": [ ... ],
  "combiners": [ ... ],
  "actions": [ ... ],
  "idle_states": [ ... ]
}
```

כל נוד כולל: `id`, `type`, `frozen`, `params`, `connections`.

---

### 12.5 Open Questions למפתח

```
⚠ OPEN QUESTION — למפתח:
פרוטוקול ה-JSON הקיים בין MacBook ל-Brain —
לתעד את הסכמה הנוכחית ולוודא תאימות עם מבנה ה-payload לעיל.
אם יש פערים — הקומפילר הוא נקודת ההתאמה.

⚠ OPEN QUESTION — למפתח:
לאמת heap זמין על ESP32-C3 SuperMini לdeserialization של 64KB.
מומלץ ArduinoJson עם StaticJsonDocument.

⚠ OPEN QUESTION — למפתח:
הקושחה של Brain צריכה להיות data-driven runtime engine.
לוודא שהארכיטקטורה הקיימת תומכת בגישה זו.
```

## 13. מצבי ממשק — DEV MODE / SHOW MODE

### 13.1 DEV MODE (ברירת מחדל)

- עריכה מלאה של הקנבס
- OTA UPLOAD זמין
- VALIDATE זמין
- כל כלי העריכה פעילים

### 13.2 SHOW MODE

- הקנבס במצב read-only — אין עריכה
- OTA UPLOAD **מושבת לחלוטין**
- מונע שינויים בשגגה תוך כדי הופעה

### 13.3 מעבר בין מצבים

- כפתור מפורש בטולבר: `DEV ↔ SHOW`
- מעבר ל-SHOW MODE דורש אישור במצב modal קצר
- מעבר חזרה ל-DEV MODE — מיידי ללא אישור


## 14. Show Runner

### 14.1 תפקיד

מסך נפרד מה-Node Editor (`/show`). מנהל את המופע המלא — סידור ליינאפ לפני ההופעה, ניווט בין נאמברים ודשבורד רשת בזמן ריצה.

---

### 14.2 מבנה המסך

**עריכה (לפני מופע — DEV MODE):**
- רשימת נאמברים קיימים — גרור ושחרר לסידור
- per-נאמבר: שם, משך משוער, `transition_fade` (ms)
- ברירת מחדל transition_fade: 500ms

**הופעה (SHOW MODE):**
- ליינאפ עם הנאמבר הנוכחי מודגש
- דשבורד בריאות רשת — per-מכשיר:
  - סטטוס חיבור: active / planned / disconnected
  - עוצמת אות (signal strength)
  - ערכי סנסור בזמן אמת לפי סוג המכשיר

---

### 14.3 ניווט בין נאמברים — Pedal

| פעולה | תוצאה |
|---|---|
| double | נאמבר הבא |
| triple | נאמבר נוכחי מהתחלה |
| triple + triple תוך 5 שניות | נאמבר קודם |

double ו-triple **שמורים למערכת** — לא זמינים בקנבס של נאמבר.
בקנבס הפדל מוגבל ל: `press`, `release`, `hold`, `short`, `long` בלבד.

---

### 14.4 מעבר בין נאמברים

```
נאמבר A נגמר
    ↓ fade (transition_fade ms)
מכשירים עוברים ל-IDLE של נאמבר B
    ↓
נאמבר B מוכן להפעלה
```

Brain מבצע interpolation (lerp) בין שני מצבי IDLE לאורך transition_fade.

```
⚠ OPEN QUESTION — למפתח:
Brain צריך לתמוך ב-lerp בין שני מצבי IDLE.
לוודא שהfirmware מממש interpolation per-device.
```

---

### 14.5 ארכיטקטורה

```
/editor  — Node Editor (בניית נאמבר בודד)
/show    — Show Runner (ליינאפ + דשבורד)
```

שני מסכים באותו Flask app. כל נאמבר הוא קובץ JSON עצמאי.


## 11. סיכום שינויים מגרסה קודמת

| פריט | שינוי |
|---|---|
| TRIGGER type: scale | הוסר — יתירות |
| SEQUENCE: interrupt port | הוסר |
| נוד OR | הוסר — מיושם דרך חיבורים מקבילים |
| MILESTONE_RESET | הוסר |
| SHOW_DURATION_SEC | עבר לנוד SHOW TIMER |
| Sound sting | הוסר — לא קיים חומרה |
| נוד SHOW TIMER | חדש |
| נוד ACCUMULATOR | חדש |
| נוד IDLE | חדש |
| Undo היסטוריה | שונה מ-20 ל-50 |
| CLIMAX_THRESHOLD | עבר לACCUMULATOR.threshold |

| Staff: סנסורים נוספים | spin_direction, orientation, impact |
| Microphone: סנסור נוסף | frequency |
| Pedal: events נוספים | short, long, double, triple |
| Pedal: נורת LED | feedback פיזי למצב רשת |
| ACCUMULATOR: decay | נוסף כאופציה — ברירת מחדל off |
| Snapshots | חדש — שמירה אוטומטית לפני OTA, 10 snapshots + REVERT |
| Resilience | חדש — התנהגות מוגדרת בנפילת מכשיר |

| fade_out | נוסף per-block על SEQUENCE — ברירת מחדל 0ms |
| priority | נוסף לTRIGGER — קובע עדיפות בקונפליקט |
| priority שווה | שגיאה חוסמת ב-VALIDATE |
| SHOW TIMER stop | מכשירים חוזרים ל-IDLE, לא Blackout |
| Device states | planned / active — מאפשר בנייה לפני קושחה |
| Show Runner | חדש — /show, ליינאפ + דשבורד + ניווט פדל |
| transition_fade | מעבר רך בין נאמברים — ברירת מחדל 500ms |
| Pedal — Show Runner | double/triple שמורים למערכת, לא זמינים בקנבס |
| CUE | לא בסקופ — SEQUENCE מספיק |
| Panic/Blackout | לא בסקופ |

---

*מסמך זה מחליף את האפיון הקודם במלואו.*
*גרסה: 2.7 | תאריך: יוני 2026*

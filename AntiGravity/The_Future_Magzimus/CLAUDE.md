# TheFutureMAGZIMUS — CLAUDE.md

## מה הפרויקט הזה
מערכת שליטה מבוזרת לניהול מופע קרקס חי.
מחברת חיישנים, אפקטים ורכיבי舞台 לתסריטים דינמיים.

---

## ארכיטקטורה

### תקשורת
```
MacBook (Flask)
    ↕ Serial (USB)
ESP32-S3 [Hub / Gateway]
    └── ESP-NOW
            ├── ESP32 → Staff        (S3 + MPU6050 + WS2812B LEDs)
            ├── ESP32 → Smoke Machine (Relay)
            ├── ESP32 → WRGB Lights  (PWM)
            └── ESP32 → Electromagnets
```

### רכיבי קצה

| רכיב | סוג | בקר | פרוטוקול |
|------|-----|-----|----------|
| Staff | משולב (input + output) | ESP32-S3 | ESP-NOW |
| מכונת עשן | פסיבי | ESP32 + Relay | ESP-NOW |
| פנסי WRGB | פסיבי | ESP32 + PWM | ESP-NOW |
| צילינדרים אלקטרומגנטיים | פסיבי | ESP32 | ESP-NOW |

---

## מצבי מערכת
- **DEV** — פיתוח ודיבוג, לוגים מלאים
- **REHEARSAL** — חזרות, כל הכלים נגישים
- **LIVE** — הופעה, ממשק מינימלי, ביצועים מקסימליים

---

## מבנה נאמבר (Number)

נאמבר הוא יחידת תוכן בסיסית במופע.
כל נאמבר מכיל **Node Tree** — עץ שמחליט מה קורה בתגובה לאירועים.

### סוגי Nodes
- **Event Node** — מאזין לטריגר (MPU input, קלט חיצוני)
- **Timeline Block** — רצף מתוזמן של פקודות למכשיר אחד

### כללי Timeline Block
- כל Timeline Block שולט במכשיר **אחד בלבד**
- מכשיר יכול להופיע במספר Timeline Blocks בנאמבר — **אך לא במקביל**
- לכל Timeline Block יש **Device Policy** מוגדרת:
  - `INTERRUPT` — מבטל טיימליין שרץ על המכשיר
  - `QUEUE` — ממתין בתור עד שהמכשיר פנוי
  - `IGNORE` — נדחה אם המכשיר תפוס

### דוגמת מבנה
```
Event: Staff rotation detected
    ├── Timeline: Staff LEDs    [policy: INTERRUPT]
    │       ├── t=0s:    color red
    │       ├── t=1.2s:  burst blue
    │       └── t=2s:    fade out
    ├── Timeline: Smoke Relay   [policy: IGNORE]
    │       ├── t=0s:    ON
    │       └── t=1.5s:  OFF
    └── Timeline: WRGB Lights   [policy: QUEUE]
            ├── t=0s:    warm white
            └── t=2s:    fade to black
```

---

## סטאק טכנולוגי

| שכבה | טכנולוגיה |
|------|-----------|
| קושחה ESP32 | C++ / PlatformIO |
| תחנת שליטה | Python / Flask |
| ממשק | Flask + Web UI (browser) |
| תקשורת Hub↔Mac | Serial (USB) |
| תקשורת Hub↔Nodes | ESP-NOW |

---

## מבנה ריפו (Monorepo)
```
TheFutureMAGZIMUS/
├── CLAUDE.md
├── firmware/
│   ├── hub/          # ESP32-S3 Gateway
│   ├── staff/        # ESP32-S3 Staff
│   ├── relay/        # ESP32 Smoke/Electromagnet
│   └── pwm/          # ESP32 WRGB Lights
├── control/
│   ├── server/       # Flask backend
│   ├── ui/           # Web frontend
│   └── engine/       # Scene/Number engine
├── numbers/          # תסריטי נאמברים (JSON/YAML)
└── docs/
```

---

## MVP — הגדרת הצלחה
נאמבר event-driven אחד שעובד end-to-end:
1. Staff שולח נתוני MPU לתחנת השליטה
2. תחנת השליטה מפעילה Timeline על Staff LEDs
3. תחנת השליטה מפעילה Relay של מכונת עשן
4. תחנת השליטה מפעילה צבע על פנסי WRGB

---

## מה לא בפרויקט הזה (עדיין)
- אפקטי LED מורכבים
- ML / generative art
- ממשק טכנאי live
- נאמברים מבוססי timecode / מוסיקה
- אינטגרציה עם הפרויקט הישן (Smart Staff v1)

---

## כללי עבודה לסוכן

### לפני כל משימה
1. קרא CLAUDE.md
2. הבן איזה חלק בארכיטקטורה נוגעת המשימה (firmware / control / engine)
3. אל תיגע בחלקים שלא רלוונטיים למשימה

### תקשורת עם המשתמש
- עברית
- תשובות קצרות, ללא preamble
- Plan לפני execute
- הסבר של שורה פשוטה על כל פעולה ומטרתה

### הפניה לפרויקט הישן
- פרויקט ייחוס: `../SmartStaff/` (או לפי הנחיית המשתמש)
- מותר ללמוד ממנו: פרוטוקולי ESP-NOW, ניהול BLE, OTA update
- אסור להעתיק: לוגיקת אפקטים, UI קיים, מערכת ML

---

## רודמאפ (לתיעוד בלבד — לא לפיתוח עכשיו)
- שלב 2: נאמברים מבוססי Timeline (timecode + מוסיקה)
- שלב 3: ממשק טכנאי live
- שלב 4: אינטגרציה עם Smart Staff v1 (generative art + ML)

## תהליך פיתוח — כללי סוכן

### קבצי ניהול
```
tasks.json           # תור המשימות — הקובץ הקנוני (orchestrator עוקב)
docs/agent/
├── DONE.md          # לוג משימות שבוצעו (קריא לאדם)
└── BACKLOG.md       # רעיונות למגירה
```

### Orchestrator
`orchestrator.py` עוקב אחרי `tasks.json`. כל שינוי בקובץ מפעיל `antigravity run claude_agent`.
**לכן: כל עדכון ל-`tasks.json` מפעיל ריצת סוכן חדשה — לעדכן בתשומת לב.**

### סטטוסים ב-tasks.json
| סטטוס | משמעות |
|-------|---------|
| `PENDING_RANKING` | הוצע, טרם אושר ותוזמן |
| `TODO` | מאושר, ממתין לביצוע |
| `IN_PROGRESS` | בעבודה עכשיו |
| `DONE` | הושלם |
| `BLOCKED` | ממתין לתלות |

### זרימת עבודה
כשהמשתמש מציע רעיון:

1. **בחינה** — האם הרעיון מקדם את ה-MVP?
2. **אם לא רלוונטי עכשיו** — שמור ב-`BACKLOG.md` עם תאריך והסבר קצר, הודע למשתמש
3. **אם רלוונטי** — הוסף ל-`tasks.json` עם `status: "PENDING_RANKING"`
4. **ביצוע** — עדכן status ל-`IN_PROGRESS` ← עבוד ← עדכן ל-`DONE`
5. **סיום** — הוסף ל-`DONE.md` עם תאריך ותיאור מה בוצע

### פורמט משימה ב-tasks.json
```json
{
  "id": "<uuid>",
  "title": "שם המשימה",
  "description": "מה זה עושה ולמה",
  "priority": 1,
  "technical_specs": {
    "required_libraries": [],
    "design_patterns": [],
    "constraints": []
  },
  "status": "PENDING_RANKING|TODO|IN_PROGRESS|DONE|BLOCKED",
  "dependencies": ["<id>"]
}
```

### פורמט DONE.md
```
## [YYYY-MM-DD] שם המשימה
מה בוצע, מה השתנה, איפה בקוד
```

### פורמט BACKLOG.md
```
## [YYYY-MM-DD] שם הרעיון
למה נדחה לעכשיו, למה זה עשוי להיות רלוונטי בעתיד
```
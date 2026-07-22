# דו״ח סשן — 2026-06-08
## נושא: Staff Vertical Green/Blue Number + אבחון ESP-NOW

---

## 1. מה בוצע

### ביטול ממשק ה-Web UI
- הוסרה השרתת הקבצים הסטטיים מ-`control/server/app.py` (הוסר `send_from_directory`, `UI_DIR`, `static_folder`)
- נתיב `/` מחזיר כעת JSON status בלבד
- הקבצים נשארו על הדיסק לעיון עתידי, רק ההגשה הופסקה

### עיצוב ופיתוח נאמבר חדש: "Staff Vertical Green/Blue"
תיאור: ראש המאסטר מאיר ירוק כשהוא אנכי-למעלה (±20° סביב 0°), כחול בכל זווית אחרת.
הלוגיקה רצה **מקומית על קושחת ה-Staff** (לא דרך ה-engine), כפריסט עצמאי המופעל ע״י CMD ייעודי חדש.

שינויי קוד שבוצעו (כולם כתובים, **טרם נצרבו לחומרה**):
- `firmware/staff/include/Protocol.h` — הוספת `CMD_LED_VERTICAL = 7`
- `firmware/staff/include/Config.h` — `LED_VERTICAL_GREEN_WINDOW_DEG = 20.0f`
- `firmware/staff/include/LedManager.h/.cpp` — פונקציות `vertical()` ו-`verticalFromFlag()`
- `firmware/staff/src/main.cpp` — state חדש `verticalActive`, טיפול ב-`CMD_LED_VERTICAL` גם אצל המאסטר וגם בסנכרון לסלייב (SyncPacket)
- `control/engine/engine.py` — מיפוי `LED_VERTICAL` ל-`cmdType=7`
- `numbers/staff-vertical-green.json` — קובץ הנאמבר עצמו

### תשתית בדיקה חיה דרך ESP-NOW
- נכתב `tools/_vertical_test.py` — כלי אד-הוק שמתחבר ל-Hub, שולח כיול, וסוטרים טלמטריה חיה (זווית/מהירות/אוריינטציה)
- אומת ש-3 המכשירים מחוברים: Master `AD44` (`/dev/cu.usbmodem1434201`), Slave `028C` (`/dev/cu.usbmodem1434301`), Hub (`/dev/cu.usbmodem143201`)

---

## 2. תגלית קריטית — כיול הוא יחסי, לא אבסולוטי
`CMD_CALIBRATE` **לא** מודד "אנכי אמיתי" — הוא מאפס את ה-bias ביחס לאוריינטציה הפיזית הנוכחית בזמן הכיול, כך שהיא הופכת ל-"זווית 0°".

**מסקנה לתהליך עבודה**: לפני כל מופע, יש לכייל את ה-Staff כשראש המאסטר מוחזק פיזית **ישר למעלה** — לא בתנוחה שרירותית.

---

## 3. בעיה פעילה — לא נפתרה
פקודות ממוקדות (`CMD_LED_SOLID` עם `targetId` ספציפי) לא נקלטות/לא נשמרות אצל המאסטר — הוא ממשיך להגיב בצבעים לפי זווית (autonomous tilt mode), בעוד שפקודת broadcast (`CMD_CALIBRATE`) עבדה בלי בעיה. גם הסנכרון מאסטר→סלייב נראה שבור (סלייב תקוע על כתום).

נבדק ואושר כתקין:
- מבנה `HubCommand` (8 בייטים) זהה בין C++ ל-Python struct packing
- `GROUP_ID=1` תואם משני הצדדים
- ה-Hub משדר broadcast גולמי ללא קשר ל-targetId
- ה-disambiguation בין `SyncPacket`/`HubCommand` (לפי `data[1]==MSG_SYNC`) לא מתנגש עם הערכים שנשלחו

עדיין לא נבדק/לא הוסבר:
- האם `EspNow::deviceId` בפועל אצל המאסטר זהה בדיוק ל-`deviceId` שמדווח בטלמטריה (`AD44`)
- האם מנגנון "Hub lost → autonomous mode" מאפס `cmdOverride` ברגע הלא נכון

---

## 4. מה מתוכנן (לפי סדר)
1. **לסיים את האבחון** — לאתר למה פקודות ממוקדות לא נקלטות אצל המאסטר ולמה סנכרון מאסטר↔סלייב לא עובד, ולתקן
2. **כיול נכון** — לכייל מחדש את ה-Staff כשהמאסטר מוחזק פיזית אנכית-למעלה
3. **המשך רצף הבדיקה החי** — זוויות נוספות, תנועות נוספות מול הטלמטריה
4. **צריבת הקושחה החדשה** (CMD_LED_VERTICAL) על שני ה-Staff, ובדיקת הנאמבר end-to-end על חומרה
5. **ניקוי** — למחוק/לעצור את `tools/_vertical_test.py` (pid=2816, רץ ברקע) כשהבדיקות יסתיימו — כלי זמני שלא אמור להישאר ב-repo

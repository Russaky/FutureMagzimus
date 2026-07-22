# DONE — לוג משימות שבוצעו

## [2026-07-22] תיקון קריטי כפול: Test on Hardware לא הגיע בכלל ל-Staff (שרת תקוע + Hub עם struct ישן)

### הבאג
המשתמש דיווח: "Test on hardware עדיין לא מגיע ל-staff אצלנו" — אחרי כל תיקוני ה-UI בסבב הקודם. בדיקה חיה חשפה **שני** גורמי שורש נפרדים, שניהם לבדם מספיקים לחסום את זה לגמרי:

**גורם 1 — שרת Flask תקוע על קוד ישן.** `ps` הראה שהתהליך (PID 1566) רץ **מאז 08:08** בבוקר, בעוד `app.py`/`protocol.py` נערכו לאחרונה ב-09:52/11:09 — השרת מעולם לא הופעל מחדש אחרי כל השינויים בסבב הקודם (כולל הוספת colorMode/pr/pg/pb/sr/sg/sb ל-`pack_effect_command`). כל בדיקה קודמת בסבב הזה שהראתה "✓ נשלח לחומרה" הייתה למעשה שולחת פורמט **ישן** (12 בייט, בלי custom color) — ה-HTTP הצליח, אבל זה לא מה שנשלח בפועל. **תוקן**: הרוג התהליך הישן (`kill 1566 1564`), הופעל מחדש (`python3 control/server/app.py &`), Hub התחבר אוטומטית.

**גורם 2 — Hub firmware עם `EffectCommand` בגודל ישן (חמור יותר).** גם אחרי הפעלת השרת מחדש, האפקט עדיין לא הגיע. `firmware/hub/include/Protocol.h` מחזיק **עותק משוכפל** (mirror) של ה-struct `EffectCommand` — ומעולם לא עודכן כשה-struct גדל ל-19 בייט ב-`firmware/staff/include/Protocol.h` (סבב effects-lab-unify-color-003). `firmware/hub/src/main.cpp:24`: `if (len == sizeof(EffectCommand)) EspNow::send(payload, len);` — ה-Hub בדק את אורך החבילה הנכנסת מול ה-`sizeof` **הישן שלו** (12 בייט), הפקודה החדשה (19 בייט) נכשלה בבדיקה ונזרקה בשקט — **אף פעם לא הגיעה ל-ESP-NOW בכלל**, לא משנה מה השרת שלח.

**תוקן**: `firmware/hub/include/Protocol.h` — עודכן `EffectCommand` ל-19 בייט (זהה בדיוק ל-Staff), עם comment מפורש שמזהיר שה-struct הזה **חייב** להישאר מסונכרן בייט-לבייט. נצרב מחדש (`pio run -e hub -t upload`) — דרש `POST /api/hub/disconnect` לפני (לשחרר את הפורט מהשרת) ו-`POST /api/hub/connect` אחרי.

### אימות — הוכחה חד-משמעית, לא רק "אין שגיאה"
נוסף Serial.print זמני ב-`main.cpp` שמדפיס בדיוק מה ה-Master קיבל (`fxCmd.templateId/paletteId/colorMode/pr/pg/pb/sr/sg/sb`), נצרב, נשלחה פקודת טסט אמיתית (Gradient, custom color, primary=אדום, secondary=כחול) תוך כדי האזנה לסריאל בו-זמנית:
```
[EFFECT RX] template=1 palette=0 colorMode=1 pr=255,0,0 sr=0,0,255
```
תואם בדיוק למה שנשלח — **הוכחה שהחומרה בפועל קיבלה ופענחה נכון**, לא רק ש-HTTP החזיר 200. ה-print הוסר אחרי האימות, נצרב build נקי סופי.

### נבדק אחרי התיקון המלא
- `pio run -e hub` נקי, נצרב, Hub מגיב ל-`/api/discover` (שני ה-staff עדיין רואים אותו).
- `pio run -e staff` (הסרת debug print) נקי, נצרב ל-Master, boot נקי (`AD44`, IMU תקין).
- Test on Hardware דרך ה-UI האמיתי (לא רק curl): `✓ נשלח לחומרה` + אומת בסריאל שהמאסטר קיבל נכון.
- Slave (`028C`) לא נגע בו — הקשר Master↔Slave (EffectSyncPacket) לא עובר דרך ה-Hub בכלל, לא הושפע מהבאג הזה.

### לקח לתיעוד
כל שינוי ל-struct משותף ב-`firmware/staff/include/Protocol.h` **חייב** להיבדק גם מול `firmware/hub/include/Protocol.h` אם ה-Hub מחזיק עותק משוכפל (mirror) — יש כרגע רק `EffectCommand` במצב הזה (לא `EffectSyncPacket`, זה Master↔Slave ישיר). כמו כן: שרת Flask מקומי **לא** מתרענן לבד — כל שינוי ב-`app.py`/`protocol.py` דורש restart ידני של התהליך, אין מנגנון auto-reload.

### קבצים
- `firmware/hub/include/Protocol.h` (עודכן — 19 בייט)
- `firmware/staff/src/main.cpp` (debug print זמני, הוסר)
- שרת Flask הופעל מחדש (לא קובץ קוד)

## [2026-07-22] Effects Lab v2: עיצוב מחדש (viewport-fit, faders אנכיים, hue-slider+hex), IMU-Reactive per-parameter, checkpoint git

### רקע וגיבוי
לפני הסבב הזה: `git commit`+`git push` של כל המצב הצבור (119 קבצים, ראה commit הקודם למעלה) לענף חדש `NO-UI` ב-`origin` — **לא ל-main**, כדי לא לגעת בו. `firmware/bridge/include/credentials.h` (SSID/password ריקים אבל מיועד להישאר מקומי לפי ה-comment שבו) הוצא מה-commit ונוסף ל-`.gitignore`. commit נוסף בסוף הסבב הזה (ראה "קבצים" למטה) — שני ה-commits יחד הם נקודת השחזור.

### באגים/בקשות שטופלו
1. **"Test on Hardware לא מגיב"** — אובחן: reflow קטן בעמוד (שינוי גובה dropdown/שורות צבע) הזיז את הכפתור ~15-20px, קליק חוזר על אותו פיקסל פספס אותו. תוקן: שורת הכפתורים הפכה ל-`position:sticky;bottom:0` — לא זזה יותר בשום מצב. אומת: 3 קליקים רצופים על אותו קואורדינטה בדיוק, 3 הצלחות עם timestamp שונה בכל אחת.
2. **עמוד גדול מה-viewport, בזבוז מקום** — עיצוב מחדש מלא: sidebar קומפקטי (230px: בורר סוג-מכשיר + רשימת אפקטים שמורים) + תוכן ראשי. כל העמוד נכנס עכשיו במסך רגיל בלי גלילה.
3. **DMX/WRGB/Progress Bar preview** — מוצג רק כש-deviceType בפועל הוא dmx/pwm/progressbar, מוסתר לגמרי (לא placeholder) כשעובדים על Staff.
4. **סליידרים אנכיים** — Speed/Intensity/Param1/Param2 הפכו לשורת faders אנכית (כמו קונסולת תאורה אמיתית), קומפקטי יותר אנכית.
5. **Toggle switch לא תקין ויזואלית** — נוספו border+shadow ברורים (היה שקוף/דהוי על רקע בהיר).
6. **Secondary color** — toggle נפרד ("Use Secondary"): נכבה כברירת מחדל, נדלק אוטומטית ונעול כש-הטמפלייט **דורש** אותו (Sparkle — spark color), אופציונלי בשאר. כשכבוי, sr/sg/sb נשלחים זהים ל-pr/pg/pb (הגרדיאנט קורס לצבע אחיד) — בלי שינוי firmware.
7. **צבע: hue slider יחיד + hex + RGB** — הוחלפו 3 הסליידרים הנפרדים (R/G/B) שנבנו בסבב הקודם ב-slider אחד שסורק את כל גלגל הצבעים (רקע rainbow-gradient) + שדה hex לכתיבה/קריאה + תצוגה נומרית R/G/B. State אמיתי (`_primaryColor`/`_secondaryColor`) מעודכן משני המקורות.
8. **IMU-Reactive per-parameter** — רשימת "פרמטר יעד" נבנית **דינמית** לפי הטמפלייט הנוכחי בפועל (למשל Fade מציג Speed/Intensity/Min Bright/Max Bright, לא "Param 1" גנרי) + אופציית **Color (Hue)** כש-Custom Color פעיל. דרש הרחבת firmware:
   - `firmware/staff/include/Protocol.h` — `ReactiveParam` קיבל `REACTIVE_PARAM_PARAM2=4` ו-`REACTIVE_PARAM_HUE=5` (אין שינוי גודל struct — reactiveParam כבר בייט גולמי).
   - `firmware/staff/src/main.cpp` — `resolveEffectParams()` מחזיר גם param2 + hue-override flag; `resolveEffectivePrimary()` חדש בונה CHSV(hue,255,255) חי כשreactiveParam==HUE; שני נקודות הרינדור (Master render + Sync send ל-Slave) עודכנו להשתמש בערכים הנפתרים, לא הסטטיים.
   - `control/server/protocol.py` — קבועים תואמים (`REACTIVE_PARAM_PARAM2`, `REACTIVE_PARAM_HUE`) לתיעוד, אין שינוי wire format.
9. **הסרת Anim Speed/FPS** — הפריוויו רץ עכשיו בקצב קבוע התואם את `TELEMETRY_MS` האמיתי של ה-firmware (50ms/20Hz), לא בקרה ידנית של המשתמש.

### נבדק — חי בדפדפן + חומרה מחוברת
- `pio run -e staff -e staff-c3` נקי, נצרב לשני הבקרים (`AD44`/`028C`), boot נקי מאומת ב-serial.
- Sparkle: Secondary נדלק ונעול אוטומטית. Fade: רשימת יעד ריאקטיבי בדיוק `Speed, Intensity, Min Bright, Max Bright, Color (Hue)`.
- בחירת Color (Hue) כיעד ריאקטיבי → סליידר ה-Hue של Primary עובר למצב מנוטרל עם תג "🔴 LIVE" (עקבי עם שאר הפרמטרים).
- Test on Hardware: 3 קליקים רצופים על אותה קואורדינטה בדיוק לאחר קונפיגורציה עם Custom Color + Color(Hue) reactive — כל השלושה הצליחו (timestamps שונים, ✓ לא נתקע).
- **לא נבדק ויזואלית על ה-LEDs הפיזיים** (אין מצלמה) — הבינדינג ל-Hue במיוחד כדאי לאמת ויזואלית (לסובב את המקל ולוודא שהצבע *הראשי* עובר בגלגל הצבעים).

### קבצים
- `firmware/staff/include/Protocol.h`, `firmware/staff/src/main.cpp`
- `control/server/protocol.py`
- `control/ui/effects.html`
- `.gitignore` (+credentials.h, +arduino_dump.*, +disassembly.txt, +claude_agent, +scratch/, +.DS_Store)
- `tasks.json`

## [2026-07-22] תיקון: Test on Hardware "לא מגיב" — הוחלף color picker נייטיבי בסליידרי RGB

### הבאג
המשתמש דיווח ש-"Test on Hardware" לא מגיב, ושהוא רוצה סליידרי RGB במקום ה-tooltip של בחירת צבע. שוחזר בדפדפן: לחיצה על ה-swatch של Primary/Secondary (`<input type=color>`) פותחת פאנל בחירת צבע נייטיבי של Chrome שמכסה את כל הכרטיסייה (כולל האזור שבו יושב "Test on Hardware") — זו בדיוק הסיבה שהכפתור "לא הגיב": הפאנל תפס את הקליקים.

### התיקון
`control/ui/effects.html` — Primary/Secondary הוחלפו מ-`<input type=color>` בודד לשלושה סליידרי R/G/B כל אחד (כמו הדפוס הקיים ב-DMX/PWM color card), עם swatch קטן לא-אינטראקטיבי שמציג את הצבע המחושב. עודכנו `customColor()` (preview), `buildEffectPayload()`, `loadEffectPayload()` לקרוא/לכתוב ישירות מה-sliders החדשים (`fx-pr/pg/pb/sr/sg/sb`) במקום parsing hex מ-color input. נוספה `updateCustomColorUI()` שמסנכרנת badges+swatches. `hexToRgb()` הוסר (לא בשימוש יותר).

### נבדק — חי בדפדפן
Gradient + Custom Color: שלושת הסליידרים לכל צבע עובדים, ה-swatch מתעדכן בזמן אמת (אדום/כחול), **אין יותר פאנל חוסם** — "Test on Hardware" הגיב מיידית ("✓ נשלח לחומרה") מיד אחרי גרירת סליידר, ללא צורך ללחוץ הרחק מפאנל פתוח קודם.

### קבצים
- `control/ui/effects.html`

## [2026-07-22] תיקון קריטי: firmware לא מסונכרן + effects-lab-unify-color-003: איחוד Legacy/Generic + צבע חופשי + Flame/Vertical + עיצוב מחדש

### הבאג המקורי
המשתמש דיווח: "כפתור בדיקה על חומרה לא תקין — מציג אפקט שגוי שבוחר בsolid". סיבת השורש: `effects-pixel-taxonomy-remap-002` שינה את המיפוי המספרי של התבניות (FX_* IDs) בקוד המקור, אבל ה-Master/Slave הפיזיים (מחוברים ב-USB) עדיין רצו את ה-firmware **הישן** מלפני השינוי — אותו ID התפרש אחרת בין UI לחומרה. תוקן ע"י צריבה מחדש של שני הבקרים (`AD44`/`028C`, מאומת נקי ב-serial אחרי כל צריבה).

### אבחון IMU-Reactive
המשתמש דיווח גם ש-IMU-Reactive "לא תקין". נבדק בזמן אמת עם Serial.print זמני (הוסר בסוף): **המנגנון עצמו תקין** — הפרמטר נפתר נכון מה-IMU החי בכל tick. הבעיה בפועל: `resolveReactiveValue(REACTIVE_SPEED)` ממפה 0-15 rad/s ל-0-255, וללא סיבוב אמיתי (מקל כמעט נייח, ~0.05 rad/s) הערך שנפתר קרוב ל-0 — נראה כמו "כבוי", לא כמו "לא עובד". המשתמש אישר בפועל אחרי סיבוב אמיתי של המקל: "עכשיו זה עובד". לא נדרש תיקון קוד.

### איחוד Legacy Effects לתוך Generic Templates (החלטת משתמש: צבע חופשי אמיתי, לא רק מיזוג UI)
1. **`firmware/staff/include/Protocol.h`** — `EffectCommand`/`EffectSyncPacket` גדלו ל-19/17 בייט: נוספו `colorMode` (palette/custom) + `pr/pg/pb` (primary) + `sr/sg/sb` (secondary). `NUM_EFFECT_TEMPLATES` גדל ל-8: `FX_FLAME`(6, Fire2012-style אמיתי) ו-`FX_VERTICAL`(7, ירוק/כחול לפי זווית, param1=חלון זווית) — משלימים את מה ש-Legacy Effect סיפק (Solid/Sparkle/Rainbow כבר היו מכוסים ע"י Solid/Sparkle/Gradient+Rainbow-palette).
2. **`firmware/staff/include/LedManager.h/.cpp`** — `resolvePalette()` חדש בונה `CRGBPalette16` מ-primary/secondary כש-colorMode=custom (2-stop gradient) — כל 8 התבניות ממשיכות לעבוד בלי שינוי נוסף כי כולן כבר עוברות דרך `ColorFromPalette()`. `genericEffect()` מקבל `const CRGBPalette16&` (במקום paletteId גולמי) + `currentAngle` (ל-FX_VERTICAL).
3. **`firmware/staff/src/main.cpp`** — globals חדשים (`fxColorMode/fxPr/fxPg/fxPb/fxSr/fxSg/fxSb`), שני call-sites של `genericEffect()` (Master render + Slave mirror) עודכנו לבנות palette דרך `resolvePalette()` ולהעביר `lastAngle`.
4. **`control/server/protocol.py`** — `_FX` struct גדל תואם (19 בייט), `pack_effect_command()` מקבל `color_mode/pr/pg/pb/sr/sg/sb`, קבועי `FX_FLAME`/`FX_VERTICAL`/`COLOR_PALETTE`/`COLOR_CUSTOM`.
5. **`control/server/app.py`, `control/engine/engine.py`** — `_dispatch_effect()`/`_dispatch_effect_preset()`: **הוסר לגמרי** ה-branch של `family=='legacy'` (הפעלת `pack_staff_command` ישירות) — כל staff effect עובר עכשיו דרך `pack_effect_command()` בלבד. `_send_effect`/`send_effect` callback מקבלים את 7 הפרמטרים הנוספים.
6. **`control/engine/effects_library.py`** — הוסר `STAFF_FAMILIES`, docstring עודכן (אין יותר "שתי משפחות").
7. **`control/ui/effects.html`** — שוכתב במלואו:
   - **הוסר טאב Legacy Effect** — רשימת Template אחת שטוחה (8 אפקטים).
   - **Toggle switch אמיתי** (לא checkbox/סליידר) לכל בחירה בינארית: Color Source (Palette/Custom), כיוון Gradient (Forward/Reverse — היה סליידר 0-255, עכשיו מתג).
   - **צבע חופשי**: כשColor Source=Custom, שני color picker (Primary/Secondary) מחליפים את בורר הפלטה.
   - **מיפוי פרמטרים דינמי מורחב** (`GENERIC_TEMPLATE_META`) — כולל Flame (Cooling/Sparking) ו-Vertical (Angle Window, max=90°, `noColor:true` שמסתיר את כל בורר הצבע כי זה אפקט-סטטוס קבוע ירוק/כחול, לא אפקט-צבע).
   - **עיצוב מחדש**: preview LED כשורה אחת (26 LEDs — תואם בדיוק למה ש-`genericEffect()` בפועל מחשב, לא ה"144" הישן שהיה קירוב לא מדויק של המראה הפיזי במטריצה). היררכיה הפוכה: הסליידרים/דרופדאונים/מתגים הם התוכן המרכזי (`.lab-main`, עמודה ממורכזת, לא כרטיסייה 360px בצד) — ספריית האפקטים השמורים הפכה לשורת "chips" קומפקטית במקום עמודת סיידבר קבועה.

### נבדק — חי, כולל חומרה מחוברת
- `pio run -e staff -e staff-c3` — נקי, נצרב לשני הבקרים, אימות boot נקי ב-serial (AD44/028C, FW v1.0.1).
- **בבדיקה חיה בדפדפן** (claude-in-chrome): Solid מסתיר את כל הפרמטרים; Vertical מסתיר את כל בורר הצבע ומראה "Angle Window (°)" עם max=90 בפועל (אומת ב-DOM: `el.max==='90'`); Gradient מראה toggle "Forward/Reverse" (לא סליידר); Custom Color מראה Primary/Secondary pickers; Flame מראה "Cooling"/"Sparking".
- **Test on Hardware** על Gradient+Custom Color (אדום→כחול): נשלח בהצלחה, אומת בלוג התעבורה האמיתי (`/api/network/traffic`): `CMD_EFFECT_STAFF template=1` ל-broadcast.
- **Save/Load round-trip**: אפקט Flame+Custom נשמר, `GET /api/fx` החזיר בדיוק `colorMode:1, pr:255/pg:0/pb:0, sr:0/sg:0/sb:255, templateId:6` — הפורמט החדש נשמר ונטען נכון. נמחק בסוף (היה טסט בלבד).

### לא נבדק
אישור ויזואלי בפועל שהצבעים/Flame/Vertical נראים נכון על ה-LEDs הפיזיים (אין גישת מצלמה) — כל מה שאומת הוא שהפקודה מגיעה נכון end-to-end ושה-firmware מרנדר לפי הקוד (נבדק בביקורת קוד + קומפילציה, לא בצילום).

### קבצים
- `firmware/staff/include/{Protocol,LedManager,EspNow}.h`, `firmware/staff/src/{LedManager,main,EspNow}.cpp`
- `control/server/{protocol,app}.py`, `control/engine/{engine,effects_library}.py`
- `control/ui/effects.html`
- `tasks.json`

## [2026-07-22] effects-pixel-taxonomy-remap-002: מיפוי מחדש ל-5 תבניות Pixel Effects (EffectComposer Proposal §5)

### מה בוצע
מיפוי/שינוי שם ל-6 התבניות הקיימות ב-`genericEffect()` כך שיתאימו לטקסונומיה של `docs/EffectComposer_Proposal_v0.1.md` §5 (Solid/Gradient/Wave/Fade/Sparkle), לפי החלטת המשתמש ("מיפוי מחדש", לא הוספה נטו לצד הקיימות). `effects/effects.json` נמצא ריק (`{"effects":{}}`) — **אין presets שמורים בפועל**, אז לא נדרש migration script; ה-IDs שונו/סודרו מחדש בחופשיות.

- **`firmware/staff/include/Protocol.h`** — `EffectTemplate` הוגדר מחדש: `FX_SOLID=0` (חדש, לא היה בסט הגנרי — fill_solid מהפלטה), `FX_GRADIENT=1` (היה Palette Cycle), `FX_WAVE=2` (היה Sinelon), `FX_FADE=3` (היה BPM), `FX_SPARKLE=4` (היה Confetti), `FX_THEATER_CHASE=5` (ללא שינוי — בונוס, אין מקבילה בהצעה). `FX_NOISE_FIELD` **הוסר** — Perlin noise על רצועה קצרה כל כך (25 LED) נראה כרעש שטוח, לא כשדה קוהרנטי; ניתן להחזיר אם הרצועה תתארך.
- **`firmware/staff/src/LedManager.cpp`** — `genericEffect()`: כל branch נכתב/נשאר לפי הסמנטיקה החדשה. שינויים פונקציונליים אמיתיים (לא רק שינוי שם): Gradient מקבל `param1`=כיוון גלילה (0-127 קדימה, 128-255 אחורה); Fade משתמש עכשיו גם ב-`param2` (היה לגמרי לא בשימוש, `(void)param2` גורף) כתקרת בהירות עליונה, לצד `param1` כתחתית — נזרק safety fallback ל-255 אם `param2<=param1`.
- **`control/server/protocol.py`** — קבועי `FX_*` עודכנו להתאים 1:1 לסדר/שמות החדשים ב-firmware.
- **`control/ui/effects.html`** — dropdown שמות עודכן; נוסף סליידר `param2` חדש (לא היה קיים בכלל — קודם תמיד נשלח `0` קשיח); נוסף **מנגנון הסתרת פרמטרים דינמי לפי תבנית** (`GENERIC_TEMPLATE_META`, עקרון WLED metadata-hiding מה-Proposal) — `speed`/`param1`/`param2` מוצגים/מוסתרים ומתויגים (למשל "Direction" ל-Gradient, "Min/Max Brightness" ל-Fade, "Density"/"Decay" ל-Sparkle) לפי מה שהתבנית הנבחרת בפועל משתמשת בו; `palette`/`intensity` תמיד גלויים (רלוונטיים לכל 6 התבניות). Preview canvas, `buildEffectPayload()`, וטעינת preset עודכנו בהתאם (כולל `param2` האמיתי, לא `0` קשיח).

### לא בוצע — היקף מכוון
פרופיל צבע primary/secondary/tertiary מלא (`colors` ב-`EffectDefinition` שב-Proposal §4) **לא** מומש — התבניות הגנריות ממשיכות לעבוד מול פלטת FastLED מובנית (`paletteId`) בלבד, לא צבעי RGB חופשיים לכל תבנית. זו הרחבת פרוטוקול (`EffectCommand` צריך שדות RGB נוספים) מעבר להיקף שסוכם (מיפוי/שינוי שם בלבד) — אם רוצים "Gradient" עם שני צבעים חופשיים ולא פלטה מובנית, זו משימה נפרדת.

### נבדק
- `pio run -e staff` ו-`pio run -e staff-c3` — שני ה-envs מתקמפלים נקי (RAM/Flash usage ללא שינוי מהותי).
- `node --check` על ה-JS המוטמע ב-`effects.html` — עובר.
- `python3 -m py_compile` על `protocol.py`/`app.py` — עובר.
- **לא נבדק על חומרה אמיתית** (לא נצרב מחדש בסשן הזה) ולא נבדק ויזואלית בדפדפן — מומלץ למשתמש לצרוב מחדש את ה-Master/Slave ולבדוק כל אחת מ-6 התבניות דרך Effects Lab לפני שימוש בהופעה.

### קבצים
- `firmware/staff/include/Protocol.h`, `firmware/staff/src/LedManager.cpp`
- `control/server/protocol.py`
- `control/ui/effects.html`
- `tasks.json`

## [2026-07-20] תיקון: ביטול קבוע של דמו "red-blue-off" שקטע פקודות ידניות

### הבאג
המשתמש דיווח שכל הזזה של הסטאף מפעילה רצף אדום→כחול→כיבוי — בדיוק ההתנהגות שתועדה כבר ב-2026-07-19 (`דוח בדיקות: כיבוי LED לא יציב ב-M2-1`, גורם שורש 3). התיקון הקודם היה workaround **per-page** (`onboarding.html`/`index.html` בלבד, מחליפים ל-`stress-test.json` בכניסה לעמוד) — לא כיסה עבודה דרך `bank.html`/`effects.html`, אז הבאג חזר.

### מיקום בקוד
`control/server/app.py`: `NUMBER_PATH` ברירת המחדל הצביע על `numbers/example.json` — Number עם אירוע יחיד `speed > 2.0` → policy `INTERRUPT` ששולח `LED_SOLID` אדום → (1.2s) כחול → (2s) `LED_OFF`, טעון תמיד ב-`engine.load(NUMBER_PATH)` בהפעלת השרת (בלי תלות בעמוד/UI).

### התיקון — הפעם באמת "נמחק לחלוטין", לא workaround
1. **`control/server/app.py`** — `NUMBER_PATH` ברירת המחדל שונה ל-`numbers/stress-test.json` (0 events) — שום Number לא נטען אוטומטית יותר. Number אמיתי נטען רק במפורש דרך `POST /api/number/load`.
2. **`numbers/example.json`** — רוקן (`events: []`) כך שגם אם מישהו יטען אותו ידנית בעתיד, הוא לא עושה כלום.

### למה זה לא פוגע בשום דבר אחר
Bank triggers (`_dispatch_bank_triggers`) ו-reactive lights (`_apply_reactive_lights`) **לא תלויים ב-`self._numbers` בכלל** — מסלולים נפרדים לגמרי ב-`Engine`. Banks וה-reactive lights ממשיכים לעבוד בדיוק כמו קודם.

### נבדק על השרת החי
- שליחת פקודת staff ידנית (ירוק) ואז הזרקת טלמטריה סינתטית עם `speed=10.0` (בדיוק התנאי שהפעיל את הדמו) — **נבדק בלוג התעבורה האמיתי**: רק הפקודה הידנית מופיעה, אין שום `CMD_STAFF` נוסף מה-engine.
- `/api/banks/triggers` ממשיך להחזיר תקין — Bank system לא נפגע.
- הוחזר ה-Staff למצב ברירת מחדל בסיום.

### קבצים
- `control/server/app.py`, `numbers/example.json`

## [2026-07-20] effects-reactive-bank-001: IMU-Reactive Effects + חיבור אפקטים ל-Banks

### מה בוצע
לפי משוב משתמש על `effects-lab-ui-001`:

1. **הוסר שדה מכשיר-פרטני/Target מ-Effects Lab** — נשאר רק סוג-מכשיר (staff/dmx/pwm/progressbar). Target/Policy נבחרים בשלב חיבור האפקט לטריגר ב-Bank, לא בעריכת האפקט. "Test" בעורך שולח תמיד ל-broadcast/all.

2. **IMU-Reactive params** — פרמטר אחד (Speed/Intensity/Param1) של אפקט Generic יכול לעקוב אחרי סיגנל IMU חי (מהירות סיבוב / זווית / אוריינטציה / כיוון סיבוב) במקום ערך קבוע. **נפתר לגמרי על ה-Master** (הוא כבר קורא את ה-IMU שלו בכל tick) — Mac רק אומר "איזה סיגנל נוהג איזה פרמטר", בלי תעבורת רדיו נוספת. `EffectSyncPacket` למסלה נשאר בדיוק באותה צורה — מקבל ערכים שכבר נפתרו.
   - `firmware/staff/include/Protocol.h`: `ReactiveSource`/`ReactiveParam` enums, `EffectCommand` גדל 10→12 בייט (2 שדות נוספים).
   - `firmware/staff/src/main.cpp`: `resolveReactiveValue()`/`resolveEffectParams()`, `lastSpeed`/`lastFlags` גלובליים חדשים (לצד `lastAngle` הקיים), משמשים גם ברינדור המקומי וגם ב-sync לסלייב.
   - `control/server/protocol.py`, `control/server/app.py`: שדות מקבילים ב-`pack_effect_command`/`/api/command/effect`.

3. **Bank action step חדש: `cmd:'EFFECT'`** — מפנה ל-effectId שמור בספרייה. `Engine._execute_step` מזהה `cmd=='EFFECT'` ומפנה ל-`_dispatch_effect_preset()` (חדש) שמדגם בדיוק את הלוגיקה של `app.py:_dispatch_effect` אבל דרך ה-callbacks הקיימים של Engine (`_send_staff`/`_send_effect`/`_send_dmx`/`_send_pwm`/`_send_progress`) — לא path נפרד. Engine מקבל `resolve_effect` callback חדש (`fx_store.get`) ו-`send_effect` callback חדש.
   - `control/ui/bank.html`: כל מכשיר (staff/pwm/progressbar/dmx — לא relay) מקבל cmd `EFFECT` נוסף ב-`DEVICES`; `PARAM_META.effectId` מסוג `effect-select` חדש שמרנדר dropdown מסונן לפי `deviceType` מתוך ספריית ה-Effects (`fxLibrary`, נטען מ-`/api/fx`).

### אומת על חומרה אמיתית
- `pio run` נקי בכל שלושת הסביבות (staff/staff-c3/hub) אחרי הרחבת הפרוטוקול.
- **תקלת צריבה על ה-Hub (לא קשורה לקוד עצמו)** — הראשונה נכשלה עם "chip stopped responding" ואז ה-chip לא הגיב בכלל, דרש **power-cycle פיזי מהמשתמש**. אחרי זה, זוהו עוד שתי תקלות שורש: (א) שרת ה-Flask הקיים (`start.sh`, מופעל מחדש אוטומטית ע"י תהליך כלשהו ב-Antigravity IDE — לא זוהה מנגנון מדויק) מחזיק את פורט הסיריאל של ה-Hub ומתחרה עם `esptool` על הפורט תוך כדי צריבה — נפתר ע"י זיהוי ה-PID המדויק, קטיעה, וצריבה מיידית לפני שחוזר. (ב) גם עם פורט פנוי, הצריבה נכשלה עם "Invalid head of packet: serial noise" בקצב ברירת המחדל — **נוסף `upload_speed = 115200`** ל-`[env:hub]` ב-`firmware/hub/platformio.ini` (תיקון קבוע, לא רק לצריבה הזו) ואז הצליחה.
- **חשוב למשתמש**: יש תהליך שמפעיל מחדש אוטומטית את `control/server/app.py` (דרך `start.sh`) בלי תלות בפעולותיי — כדאי לבדוק מה מגדיר את זה (run-configuration ב-Antigravity IDE?) אם רוצים לצרוב מחדש בעתיד בלי התנגשויות.
- Master (S3 `AD44`) ו-Slave (C3 `028C`) נצרבו מחדש בהצלחה.
- מחזור מלא דרך השרת החי: אפקט IMU-reactive (`angle→speed` על Palette Cycle) נשלח ל-Master — טלמטריה המשיכה לזרום תקין (אין קריסה), ניטור סריאל ישיר על ה-Master תוך כדי — אין שגיאות.
- **אינטגרציית Bank מלאה, מקצה לקצה**: אפקט נשמר → Bank נוצר עם מיפוי `catch → EFFECT step` → הופעל כ-Active → הופעל synthetic trigger דרך `/api/trigger/test` → **אומת בלוג התעבורה האמיתי** (`/api/network/traffic`): `CMD_EFFECT_STAFF` נשלח בפועל ל-`FFFF` (broadcast) עם הפרמטרים הנכונים.

### לא נבדק
אישור ויזואלי שהאפקט ה-reactive באמת "עוקב" אחרי תנועה פיזית של המקל (רק אושר שהטלמטריה זורמת וש-firmware מתקמפל/עולה נקי) — אין גישת מצלמה. מומלץ למשתמש להניע את הסטאף עם אפקט reactive פעיל ולוודא ויזואלית שהצבע/העוצמה משתנים בהתאם.

### קבצים
- `firmware/staff/include/{Protocol,EspNow,LedManager}.h`, `firmware/staff/src/{EspNow,LedManager,main}.cpp`
- `firmware/hub/include/Protocol.h`, `firmware/hub/platformio.ini` (upload_speed)
- `control/server/{protocol,app}.py`, `control/engine/engine.py`
- `control/ui/{effects,bank}.html`
- `tasks.json`

## [2026-07-20] effects-lab-ui-001: Effects Lab — מודול UI לעיצוב ושמירת אפקטים

### מה בוצע
מודול חדש בממשק, `/effects.html` ("Effects Lab"), בונה על `staff-generic-fx-001` (למטה): עורך אפקטים מלא לפי מכשיר, עם ספריית פריסטים שמורה.

- **`control/engine/effects_library.py`** — `EffectStore`, אותו דפוס בדיוק כמו `bank_manager.BankStore` (atomic JSON write ל-`effects/effects.json`, אין DB).
- **`control/server/app.py`** — `GET/POST /api/fx`, `GET/PUT/DELETE /api/fx/<id>`, `POST /api/fx/<id>/test` (שליחה חד-פעמית לחומרה של פריסט שמור), `POST /api/fx/preview` (בדיקה של אפקט שעוד לא נשמר). כל הדיספאץ' עובר דרך `_dispatch_effect()` שמשתמש **באותם** `proto.pack_*` functions כמו שאר ה-endpoints — לא נוצר מסלול שידור נפרד.
- **`control/ui/effects.html`** (נכתב מחדש, היה mockup לא-מוגש) — 3 עמודות: רשימת פריסטים שמורים (עם מחיקה), תצוגה מקדימה בקנבס (144 LEDs + preview צבע ל-DMX/WRGB/Progress Bar), ועורך. העורך תלוי-מכשיר: Staff מציע Generic Template (6 תבניות × 6 פלטות + speed/intensity/param1, תואם ל-`EffectCommand`) או Legacy Effect (6 הפקודות הקבועות), בעוד DMX/WRGB/Progress Bar מציעים רק צבע סטטי (+fade איפה שהפרוטוקול תומך) — **בהתאם ליכולות המכשיר בפועל**, לא מומצא.
- נרשם route (`/effects.html`) ופריט ניווט חדש ב-`nav.js`.

### נבדק
- `py_compile` על `app.py`+`effects_library.py`, `node --check` על ה-JS המוטמע.
- מחזור CRUD מלא מול השרת החי (לא סימולציה): יצירת אפקט → הופיע ברשימה → **בדיקה מול חומרה אמיתית** (`/api/fx/<id>/test`) — Master המשיך לשדר טלמטריה טרייה מיד אחרי (אין קריסה) → עדכון (`PUT`) → מחיקה → רשימה ריקה שוב.
- נבדק גם `/api/fx/preview` (אפקט לא-שמור) על DMX.
- בסיום הוחזר ה-Staff למצב ברירת המחדל (`CMD_LED_TILT`).

### לא נבדק
תצוגה ויזואלית בדפדפן בפועל (אין claude-in-chrome מחובר בסשן זה) — נבדק רק ש-`GET /effects.html` מחזיר 200 ושה-JS תחבירית תקין. מומלץ למשתמש לפתוח את העמוד ולוודא שהעריכה/השמירה עובדות גם דרך ה-UI בפועל, לא רק דרך ה-API.

### קבצים
- `control/engine/effects_library.py` (חדש)
- `control/server/app.py`
- `control/ui/effects.html`, `control/ui/nav.js`
- `tasks.json`

## [2026-07-20] staff-generic-fx-001: מנוע אפקטים גנרי מבוסס FastLED ל-Staff (Master+Slave)

### מה בוצע
במקום עוד CmdType קבוע לכל אפקט חדש, נוסף מנגנון גנרי: 6 תבניות FastLED (Palette Cycle / Noise Field / Sinelon / BPM / Confetti / Theater Chase) × 6 פלטות מובנות (Rainbow/Heat/Lava/Ocean/Forest/Party), עם פרמטרים משותפים (templateId, paletteId, speed, intensity, param1, param2). "אפקט חדש" = preset פרמטרים חדש, ללא flash נוסף.

מומש כתוספת **מבודדת לחלוטין** מ-6 האפקטים הקיימים (Solid/Sparkle/Flame/Rainbow/Vertical/Off) — לא נגעתי ב-`HubCommand`/`SyncPacket`/ה-switch הקיים. לקח מפורש מ-postmortem קודם (למטה, 2026-06-08): `HubCommand`/`SyncPacket` שניהם 8 בייט התנגשו כי הדיספאץ' היה size-only. ה-struct/msgType החדשים (`EffectCommand`=`MSG_CMD_EFFECT`=0x52, `EffectSyncPacket`=`MSG_SYNC_EFFECT`=0x51, שניהם 10 בייט — אותו גודל כמו `PairingAck`) נבדקים ב-`onRecv` לפי msgType מפורש **לפני** כל fallback לפי גודל בלבד, באותו דפוס בדיוק כמו `SyncPacket`.

מיראור למסלה: `EffectSyncPacket` נשלח **במקום** (לא בנוסף ל-) `SyncPacket` הרגיל באותו tick — לקח מ-root-cause-2 (2026-07-19 למטה): esp_now_send נוסף לכל tick הציף את הרדיו והפיל sync packets.

### קבצים
- `firmware/staff/include/Protocol.h` — `EffectCommand`, `EffectSyncPacket`, `EffectTemplate`, `EffectPalette`, `MSG_CMD_EFFECT`, `MSG_SYNC_EFFECT`.
- `firmware/staff/include/EspNow.h/.cpp` — תורים חדשים, guard מפורש ב-`onRecv`, `sendEffectSyncPacket`, `sendEffectList` מרחיב את הרשימה (IDs 6-11).
- `firmware/staff/include/LedManager.h/.cpp` — `genericEffect()` מיישם את 6 התבניות (palettes, `inoise8`, `beatsin8/16`, `fadeToBlackBy`).
- `firmware/staff/src/main.cpp` — `genericEffectActive` state, דיספאץ' ה-EffectCommand, שילוב ברינדור המאסטר, sync send יחיד למחזור (mutually exclusive), וטיפול בסלייב (שני סוגי sync packet).
- `firmware/hub/include/Protocol.h`, `firmware/hub/src/main.cpp` — `EffectCommand` (mirror), `MSG_CMD_EFFECT_STAFF`=0x16 (שכבת ה-serial Mac↔Hub, נפרד מ-msgType ברמת ה-ESP-NOW), passthrough גנרי (אותו דפוס כמו שאר הפקודות).
- `control/server/protocol.py` — `pack_effect_command()`, קבועי `FX_*`/`PAL_*`.
- `control/server/app.py` — `POST /api/command/effect`.

### נבדק — על חומרה אמיתית (לא סימולציה)
- `pio run` נקי בשלושת הסביבות: `staff` (S3/Master), `staff-c3` (C3/Slave), `hub`.
- **באג שנתפס ותוקן בקומפילציה**: שמות אפקט ("PALCYCLE"/"CONFETTI") ארוכים מדי ל-`char[8]` ב-`sendEffectList()` — קוצרו ל-"PALCYC"/"CONFETI".
- זוהו הבקרים הפיזיים בבטחה לפני צריבה (`esptool chip_id`, לא הורס): Master=ESP32-**S3** `AD:44`, Slave=ESP32-**C3** `02:8C` — תואם לתיעוד הקודם.
- נצרב מחדש דרך USB ישיר (לא OTA) לשני הבקרים — שניהם עלו נקי.
- שרת ה-Flask (שכבר רץ אצל המשתמש) הופעל מחדש כדי לטעון את הקוד החדש — התחבר אוטומטית ל-Hub (`/dev/cu.wchusbserial5C371995561`), `/api/discover` מחזיר את שני הבקרים (`AD44`, `028C`, שניהם `role:staff`), Master משדר StaffTelemetry חי ותקין (angle/speed/orientation/flags) — מוכיח שה-firmware החדש לא שבר את מסלול הטלמטריה הקיים.
- נשלחו מספר פקודות `/api/command/effect` בזמן אמת (כל 6 התבניות, פלטות שונות, גם broadcast וגם target ספציפי ל-Master בלבד) — כולן חזרו `ok:true`, וMaster המשיך לשדר טלמטריה טרייה ורציפה אחרי כל אחת (הוכחה שהלולאה הראשית לא נתקעה/קרסה/עשתה watchdog reset).
- ניטור סריאל ישיר (USB דיבוג, לא דרך ה-Hub) על שני הבקרים בו-זמנית תוך כדי שליחת הפקודות — **אין** פלט שגיאה/Guru Meditation/boot loop.
- בסיום: נשלח `CMD_LED_TILT` (broadcast) כדי להחזיר את שני הראשים למצב ברירת המחדל (זווית→צבע) ולא להשאיר את החומרה במצב טסט.

### לא נבדק / מגבלה ידועה
**לא אומת ויזואלית שהצבע/האנימציה בפועל על הלדים נכונים** — אין גישת מצלמה לחומרה הפיזית בסביבה זו. מה שכן אומת: הפקודה עוברת בהצלחה מקצה לקצה (Mac→Hub→ESP-NOW), שני הבקרים נשארים חיים ומגיבים, ואין קריסה. מומלץ למשתמש לאשר ויזואלית שהאפקטים נראים כמצופה על ה-Staff הפיזי.

עדיין לא בוצע (מחוץ להיקף שהושלם): ספריית Effects שמורים/UI לעריכה (הוחלט קודם עם המשתמש לשלב Bank/UI בהמשך) — כרגע רק `/api/command/effect` חד-פעמי קיים, ללא שמירה/הצגה בממשק.

### קבצי ניהול
- `tasks.json` — `staff-generic-fx-001` → `DONE`.

## [2026-07-20] bank-edge-ui-004: Timeline Drag & Drop + כרטיסיית עריכה יחידה
`control/ui/bank.html` — כרטיסיית העריכה היחידה (side panel `#step-panel`) כבר הייתה קיימת מ-bank-edge-ui-003: לחיצה על קובייה טוענת אותה לחלונית הצד, לחיצה על ריק בציר מוסיפה קובייה חדשה ובוחרת אותה. הושלם בקובייה זו: תמיכת **Drag & Drop** (HTML5 native) להזזת קוביות לאורך ה-Timeline —
- קוביות קיבלו `draggable="true"` + `cubeDragStart`/`cubeDragEnd`.
- הטראק (`.timeline-track`) מטפל ב-`trackDragOver`/`trackDragLeave`/`trackDrop`: משחרור העכבר מחושב `t` חדש לפי מיקום ה-X היחסי בטראק, הקובייה מסודרת מחדש במערך `steps` (sort), וה-selection עוקב אחריה.
- הגרירה מוגבלת לאותו בלוק/מכשיר (אי אפשר לגרור קובייה בין טראקים שונים).

## [2026-07-20] hub-reconnect-001: תיקון באג "Hub לא מחובר" + Auto-Reconnect + כפתורי חיבור בממשק

### הבאג
המשתמש דיווח שהממשק מציג "hub not connected" למרות שה-Hub מחובר פיזית. אבחון:
- `control/server/app.py` יצר את ה-`bridge` (Serial Mac↔Hub) **פעם אחת בלבד** בהפעלת השרת, מול `SERIAL_PORT` קבוע (ברירת מחדל `/dev/tty.usbserial-0001`).
- אם הפתיחה נכשלת — השגיאה נתפסת בשקט ומודפסת רק לקונסולה; `bridge` נשאר `None` **לצמיתות**, וכל endpoint שתלוי בו (`/api/hub/pause`, `/api/wifi`, `/api/discover` וכו') מחזיר `"hub not connected"` בלי שום קשר למצב הפיזי בפועל.
- **אין reconnect בכלל** — אם ה-Hub מתנתק ומתחבר מחדש תוך כדי ריצת השרת (USB), אין שום מנגנון שמזהה זאת.
- **אומת חי**: השרת שכבר רץ על המחשב (port 5000, אותו תהליך שהמשתמש עובד מולו) נמצא עם `bridge=None` (אין file descriptor של סריאל פתוח בכלל) — כלומר זו בדיוק התקלה שדווחה, לא השערה. `/dev/tty.usbserial-0001` לא קיים כלל במחשב הזה; הפורט האמיתי של ה-Hub הוא `/dev/cu.wchusbserial5C371995561` (גשר CH340/WCH).

### התיקון
1. **`control/server/serial_bridge.py`** — נוסף callback `on_disconnect`, נורה גם מלולאת הקריאה (`_run`, על `SerialException`) וגם מ-`send()` (כתיבה לפורט שנעלם) — כך ניתוק פיזי אמצע-ריצה מזוהה מיידית, לא רק בהפעלה.
2. **`control/server/app.py`**:
   - `SERIAL_PORT` בברירת מחדל הוא כעת `None` (לא פורט קשיח) — משתמש ב-auto-detect אם לא הוגדר מפורשות ב-env.
   - `_guess_hub_port()` — סורק `serial.tools.list_ports.comports()` במדורג לפי רמת ביטחון: קודם שבבי גשר UART חיצוניים ידועים (CH340/CH9102/CP210/WCH), אחר כך "usbserial" גנרי, ולבסוף "usbmodem"/"uart" (רמת ביטחון נמוכה — יכול להיות גם ה-USB הנטיבי/JTAG של אותו בקר, בדיוק התקלה שתועדה ב-2026-07-16 למעלה: "ה-Hub חובר בטעות לפורט הנטיבי").
   - `_connect_hub()`/`_disconnect_hub()`/`_on_hub_lost()` — ניהול מצב idempotent עם `_hub_lock`; ניתוק ידני מפורש (`_hub_manual_disconnect`) מבדיל בין "המשתמש ניתק בכוונה" ל"התנתק פיזית" — ה-watchdog לא ינסה להתחבר מחדש אחרי ניתוק ידני.
   - `_hub_watchdog()` — thread רקע, כל 2 שניות (`HUB_RECONNECT_INTERVAL_SEC`) מנסה `_connect_hub()` אם אין חיבור פעיל ולא בוצע ניתוק ידני — replug פיזי מתאושש לבד תוך כ-2 שניות בלי פעולת משתמש.
   - Endpoints חדשים: `GET /api/hub/status`, `GET /api/hub/scan` (רשימת פורטים + ניחוש), `POST /api/hub/connect` (`{port?}` — ריק=auto), `POST /api/hub/disconnect`.
   - `_tx()` עוטף את `bridge.send()` ב-`try/except serial.SerialException` (היה עלול לזרוק 500 לא מטופל אם הפורט נעלם תוך כדי שליחה).
3. **`control/ui/nav.js`** (מוזרק לכל 5 העמודים שמוגשים בפועל — `index/dashboard/measure/onboarding/bank.html`) — widget סטטוס Hub בתחתית הסיידבר (נקודה + "Hub", לוחצים לפתיחת פאנל עם 3 כפתורים: 🔍 חפש / 🔌 התחבר / ⛔ נתק + רשימת פורטים שנסרקו), ו**באנר אדום קבוע בראש המסך** בכל דף כשה-Hub לא מחובר (עם כפתור "התחבר" ישיר). פולינג עצמאי על `/api/hub/status` כל 2 שניות — לא תלוי בטעינת socket.io (חלק מהדפים, כמו `measure.html`/`onboarding.html`, לא טוענים אותו).

### נבדק
- `python3 -m py_compile app.py serial_bridge.py` — עובר.
- `node --check nav.js` — עובר.
- `Flask test_client` על כל 4 ה-endpoints החדשים: status ריק בהתחלה, scan מחזיר את 6 הפורטים האמיתיים של המחשב עם ניחוש נכון (`wchusbserial...`, לא `usbmodem...` הנטיבי), connect לפורט לא קיים נכשל בעדינות עם הודעת שגיאה (לא קורס), status אחרי כשל משקף את השגיאה, disconnect מנקה מצב.
- **לא הופעל connect אמיתי מול החומרה הפיזית** — השרת של המשתמש כבר רץ (PID קיים על port 5000) ופוטנציאלית מחזיק את אותו פורט; לא ניסיתי לפתוח אותו פעמיים כדי לא להפריע לסשן החי.
- לא נבדק ויזואלית בדפדפן (אין claude-in-chrome מחובר בסשן זה).

### פתוח / דורש פעולת משתמש
**השרת הרץ כרגע (port 5000) טוען את הקוד הישן** — צריך restart כדי לטעון את התיקון. המשתמש צריך לאשר/לבצע את זה בעצמו (לא הופעל ריסטארט אוטומטית לתהליך רץ).

### קבצים
- `control/server/serial_bridge.py`, `control/server/app.py`, `control/ui/nav.js`, `tasks.json`.

## [2026-07-20] Microphone — תמיכת ESP32-S3 + מצב DEV (USB ישיר) + צריבה לחומרה אמיתית

### מה בוצע
מימוש `docs/microphone_spec.md` (נכתב באותה ישיבה): הרחבת `firmware/mic/` (שהיה C3+MAX9814+ESP-NOW בלבד, `spec-fw-003`) לתמיכה גם ב-ESP32-S3 כברירת מחדל, עם מצב DEV נוסף מעל USB ישיר.

1. **`firmware/mic/include/SerialBridge.h` + `src/SerialBridge.cpp`** — הועתקו כלשונם מ-`firmware/hub/` (אותו פרוטוקול framed `0xAA55`+CRC8-SMBUS בדיוק כמו ש-Hub משתמש בו מול Mac).
2. **`firmware/mic/include/Config.h`** — `MIC_ADC_PIN` הפך ל-`#ifndef` עם fallback ל-GPIO0 (C3, ללא שינוי התנהגות לenv הקיים), ניתן לדריסה per-env.
3. **`firmware/mic/platformio.ini`** — נוסף `env:mic-s3` (+`mic-s3-ota`): `board=esp32-s3-devkitc-1`, `MIC_ADC_PIN=1`, `flash_size=4MB`. `default_envs` עודכן ל-`mic-s3`. `env:mic` (C3) נשאר ללא שינוי — לא הוחלף, לפי החלטת §7 באפיון.
4. **`firmware/mic/src/main.cpp`** — מנגנון DEV/PRODUCTION (§2.3 באפיון): `Serial.isConnected()` (HWCDC, בודק USB CDC/DTR אמיתי מול host — לא VBUS) קובע האם לשלוח את אותו `MicTelemetry` דרך `SerialBridge::sendFrame()` (USB ישיר) או דרך `esp_now_send()` (ברירת מחדל). `Serial.begin()` הוחלף ב-`SerialBridge::begin()`.

### קבצים ששונו
- `firmware/mic/include/SerialBridge.h`, `firmware/mic/src/SerialBridge.cpp` (חדשים)
- `firmware/mic/include/Config.h`, `firmware/mic/platformio.ini`, `firmware/mic/src/main.cpp`

### בדיקות — על חומרה אמיתית
- `pio run -e mic-s3` ו-`pio run -e mic` (C3) — שני ה-envs מתקמפלים נקי.
- **באג שנתפס ותוקן:** `env:mic-s3` הראשון נכנס ל-boot loop אינסופי (ROM bootloader חוזר על עצמו כל ~16ms, לעולם לא מגיע ל-`setup()`) — גם אחרי `erase_flash` מלא. סיבה: `board_build.partitions` ברירת המחדל של `esp32-s3-devkitc-1` היא `default_8MB.csv`, לא תואמת ל-`flash_size=4MB` שהוגדר בפועל (partition `app1` חורג מעבר ל-4MB). תוקן עם `board_build.partitions = min_spiffs.csv` (אותו פתרון כמו ב-`staff-s3` הקיים). תועד ב-`docs/LESSONS_LEARNED.md` §15.
- זוהה הפורט הפיזי הנכון מבין 3 מכשירים מחוברים לפי USB descriptor (`system_profiler SPUSBDataType`): `usbmodem142401` = VID `0x303a` (Espressif native USB) + `invalid header: 0xffffffff` (flash ריק) לפני הצריבה — לעומת השניים האחרים ששייכים למכשיר קיים אחד עם גשר WCH (VID `0x1a86`).
- אחרי התיקון: המכשיר עלה נקי ומשדר `MicTelemetry` דרך USB (מצב DEV) כל 50ms — `deviceId=43988` (תואם ל-MAC בפועל), rms/peak/frequency מתעדכנים, CRC תקין באופן עקבי.
- **Dashboard/Control readiness:** `control/server/serial_bridge.SerialBridge` (בדיוק אותה מחלקה ש-`app.py` משתמש בה) חובר ישירות לפורט הפיזי של המכשיר — `on_mic_telemetry` callback נורה עם דאטה מפוענח נכון. לא הופעל מול שרת ה-Flask הרץ בפועל (יש session פעיל על פורט 5000 עם `SERIAL_PORT` ברירת מחדל — לא הופרע). קוד ה-UI (`dashboard.html`, `planner.html`, `editor.html`) כבר תומך ב-role `mic`/`mic_telemetry` end-to-end מ-`spec-proto-001`/`spec-eng-001` — לא נדרש שינוי.
- לא נבדק עדיין: מעבר בפועל למצב PRODUCTION (ניתוק USB, שידור על ESP-NOW דרך Hub אמיתי) — דורש Hub מחובר באותה רשת.

### עדכון — תיקון פין + אימות מחיאת כף (אותו יום)
בדיקה ראשונית (12+15 שניות האזנה, מחיאות כפיים) הראתה peak שטוח לחלוטין (0.0013–0.0043, ללא תגובה) — חשד לבעיית חיווט. המשתמש אישר: ה-OUT של MAX9814 מחובר בפועל ל-**GPIO4**, לא GPIO1 כפי שהוגדר ב-`MIC_ADC_PIN` (ניחוש ראשוני באפיון, לפני אימות חיווט בפועל). תוקן ב-`platformio.ini` (`-D MIC_ADC_PIN=4`), `Config.h` (הערה), ו-`docs/microphone_spec.md` §3 (טבלת פינים). נצרב מחדש — מחיאת כף בודדת זוהתה בבירור: `peak=0.2438` (פי 14.3 מ-baseline ~0.017), `rms=0.0185`. מאשר: החומרה (MAX9814 + ADC + חישוב RMS/peak ב-firmware) תקינה end-to-end.

### פתוח
ערכי כיול מדויקים (`baseline_rms`/`applause_peak_threshold` ל-Config.h) עדיין לא נקבעו — הבדיקה הנוכחית הייתה איכותית (אישור שהחיישן מגיב), לא ישיבת כיול מלאה מול אולם אמיתי, לפי §6 באפיון.

## [2026-07-20] bank-edge-ui-002: Bank Manager UI — Priority Field

### מה בוצע
נוסף שדה עדיפות (`priority`) לכל אחד מ-6 כרטיסי הטריגרים ב-`bank.html`. ה-backend כבר תמך בזה במלואו (`bank_manager.BankStore.update(priorities=...)` ו-`PUT /api/banks/<id>` שנוספו ב-`bank-edge-backend-002`) — המשימה הייתה רק ה-UI. נוסף input מספרי (`#priority-<key>`) בראש כל `trigger-card`, מוצג לצד שם הטריגר, מאותחל מ-`bank.priorities[key]`. שינוי (`onchange`) קורא ל-`updatePriority(key, value)` חדשה, ששולחת `PUT /api/banks/<id>` עם `{ priorities: { [key]: value } }` — נשמר אוטומטית ל-JSON של ה-Bank דרך `BankStore._save()` הקיים (אין שינוי backend נדרש).

### קבצים ששונו
- `control/ui/bank.html` — CSS ל-`.trigger-priority`; input עדיפות ב-`renderEditor()`; פונקציה חדשה `updatePriority()`.

### בדיקות
לא הורץ שרת בפועל (אין גישה לדפדפן בסביבה זו) — נבדק ויזואלית מול מבנה ה-API הקיים (`PUT /api/banks/<id>` כבר תומך ב-`priorities` מאז `bank-edge-backend-002`, ו-`bank.priorities` מוחזר תמיד מ-`BankStore.list()`/`get()` הודות למיגרציה ב-`_load()`). מומלץ לבדוק ידנית בדפדפן שהערך נשמר ומוצג נכון אחרי רענון.

## [2026-07-20] bank-edge-backend-002: Backend Engine — Connection Watchdog & Trigger Priority

### מה בוצע
נוספו שני מנגנוני edge-case ל-Engine, שניהם דורשים מ-`bank-engine-001`:

1. **Connection Watchdog** — מחלקה חדשה `ConnectionWatchdog` (thread ברקע, `daemon=True`, אותו סגנון כמו `ShowTimer`/`Accumulator` הקיימים): `touch()` מאפסת טיימר; אם עוברות 3000ms (`STAFF_WATCHDOG_TIMEOUT_SEC`) בלי `touch()` — נורה `on_timeout` פעם אחת (לא חוזר על עצמו בכל poll, רק כשה-touch הבא מגיע). `Engine.on_telemetry()` (שמקבל אך ורק StaffTelemetry) קורא ל-`touch()` בכל פקט. בטיים-אאוט: `_on_staff_watchdog_timeout()` מבטל את כל הטיימליינים הפעילים (`registry.cancel_all()`) ומחזיר את כל המכשירים למצב ה-IDLE הרשום (`registry.apply_all_idles()`) — בדיוק כמו האיפוס שקורה כיום ב-`show_timer_start()`. נורה גם אירוע `watchdog_timeout` דרך `_emit` (זורם אוטומטית ל-WebSocket דרך `_engine_event` הקיים ב-`app.py`, אין צורך בשינוי wiring).

2. **Priority-based Dispatch** — נוסף פרמטר `priority` (int, ברירת מחדל 0 — שומר תאימות מלאה לאחור לכל Number event קיים) ל-`DeviceRegistry.run()`: אם ה-priority הנכנס **גבוה** מזה של הטיימליין הפעיל על אותו מכשיר — קטיעה מיידית **בלי קשר ל-Device Policy** של הבלוק החדש. אם הוא **נמוך** — נדחה תמיד ולא יכול לקטוע, גם אם ה-policy שלו מוגדר `INTERRUPT`. רק כשה-priority **שווה** (המקרה הרגיל, 0==0) חוזרת ההתנהגות המקורית לפי INTERRUPT/QUEUE/IGNORE. כך "טריגרים כפולים" (Spin+Toss על אותו פקט טלמטריה) נפתרים תמיד לפי סדר ה-priority בלי קשר לסדר העיבוד בלולאה. עדיפויות ברירת מחדל ל-6 הטריגרים הקבועים הוגדרו ב-`bank_manager.DEFAULT_TRIGGER_PRIORITY` (catch=60, toss=50, fast_spin=40, roll=30, static_vertical=20, static_horizontal=10 — אירועים רגעיים/משמעותיים גוברים על מצבי תנועה מתמשכים). `BankStore` שומר `priorities` per-bank (עם מיגרציה אוטומטית ל-Banks ישנים שנטענים בלי השדה) ו-`update()`/`active_priorities()` תומכים בו; ה-mapping format (`mappings[key] = timelines`) לא השתנה — כדי לא לשבור את `bank.html` הקיים.

### קבצים ששונו
- `control/engine/engine.py` — מחלקה חדשה `ConnectionWatchdog`; `Engine.__init__` יוצר `_staff_watchdog`; `on_telemetry` קורא `touch()`; `_fire_bank_action` מעביר priority מה-Bank הפעיל; `_fire_event` מקבל `priority` ומעביר אותו ל-`registry.run()`.
- `control/engine/device_registry.py` — `run()` מקבל `priority`, משווה מול `_active_priority` (dict חדש) לפני החלת ה-policy; `_start`/`_on_done`/`cancel_all`/`_cancel_device` עודכנו לתחזק אותו.
- `control/engine/bank_manager.py` — `DEFAULT_TRIGGER_PRIORITY`, `BankStore.create/update/active_priorities` תומכים ב-`priorities`, מיגרציה ב-`_load()`.
- `control/server/app.py` — `PUT /api/banks/<id>` מקבל `priorities` בבקשה; `GET /api/banks/triggers` מחזיר גם `defaultPriorities` (לשימוש עתידי ב-`bank-edge-ui-002`, שטרם אושרה).

### בדיקות
נבדק end-to-end ללא חומרה (`Engine`/`DeviceRegistry` standalone): (1) Watchdog — הרצת טיימליין ידני על relay, המתנה מעבר ל-timeout מקוצר לבדיקה, אימות ש-`watchdog_timeout` נורה פעם אחת ושה-relay חזר ל-IDLE שנרשם. (2) Priority — עם `FakeTimeline` ישיר על `DeviceRegistry.run()`: priority גבוה קוטע פעיל נמוך גם עם policy=IGNORE; priority נמוך לא קוטע פעיל גבוה גם עם policy=INTERRUPT; priority שווה חוזר להתנהגות policy הרגילה (INTERRUPT קוטע, IGNORE נדחה). (3) תרחיש Bank מלא — פקט טלמטריה יחיד עם `fast_spin`+`toss` שניהם edge יחד: `toss` (50) ניצח את `fast_spin` (40) בלי תלות בסדר העיבוד בלולאה (נבדק גם בכיוון ההפוך — `toss` יורה קודם, `fast_spin` מגיע אחרי ולא מצליח לקטוע). לא נבדק על חומרה אמיתית.

## [2026-07-20] bank-manager-ui-001: Bank Manager Web UI (Preset Groups)

### מה בוצע
נבנה עמוד `control/ui/bank.html` — ממשק CRUD מלא ל-Banks: פאנל צד עם רשימת Banks (יצירה/מחיקה/בחירה, נקודת "Active" ירוקה על ה-Bank הפעיל), ואזור עריכה עם 6 כרטיסי הטריגרים הקבועים (Fast Spin / Toss / Roll / Catch / Static Horizontal / Static Vertical). לכל טריגר: צ'יפים המסכמים את הפעולה הממופה, כפתור "ערוך פעולה" הפותח מודל בונה-פעולה (בחירת מכשיר Staff/Relay/PWM/DMX/ProgressBar, Target ID, Policy, ורשימת steps עם `t` + `cmd` ופרמטרים ספציפיים לכל פקודה — תואם 1:1 ל-`_execute_step()` ב-`engine.py`), וכפתור "נקה". מספר בלוקי-מכשיר לכל טריגר נתמך (מיפוי = מערך `timelines` מלא, בדיוק כמו שהתיעוד ב-`bank_manager.py` מגדיר). "הפוך לפעיל"/"בטל" קורא ל-`POST/DELETE /api/banks/.../activate`. נבנה בווניל HTML/JS + `shared.css` (MD3 light theme) — תואם לשאר עמודי ה-UI בפרויקט (`planner.html`, `composer.html`) ולא ל-React/Tailwind שצוינו ב-spec המקורי, כי אין תשתית build בפרויקט בכלל.

### קבצים חדשים
- `control/ui/bank.html`

### קבצים ששונו
- `control/server/app.py` — נוסף route `GET /bank.html` (לפי התבנית הקיימת של routes מפורשים ל-`control/ui/`).
- `control/ui/nav.js` — נוסף פריט ניווט "Banks" לסיידבר.

### בדיקות
נבדק end-to-end מול שרת Flask מקומי ללא חומרה (עותק זמני על פורט חלופי כדי לא לגעת בשרת הפיתוח הרץ של המשתמש על 5000): `GET /bank.html`→200, יצירת Bank, מיפוי `toss` לשני בלוקים (Relay + PWM) עם steps, `GET` לאימות מבנה ה-JSON שנשמר, הפעלה כ-Active, `GET /api/banks` לאימות `activeId`, ביטול הפעלה, ניקוי מיפוי, ומחיקת ה-Bank — כל הקריאות חזרו `ok:true` עם המבנה הצפוי. לא נבדק ויזואלית בדפדפן (אין גישה ל-UI אינטראקטיבי בסביבה זו) ולא נבדק על חומרה אמיתית.

### מה בוצע
נוסף מנגנון "Bank" ל-Engine: פריסט של מיפוי בין 6 טריגרים קבועים של תנועת הסטאף (`fast_spin`, `toss`, `roll`, `catch`, `static_horizontal`, `static_vertical`) לפעולות רשת (Relay / PWM / DMX / Staff / ProgressBar). בכל רגע קיים "Bank פעיל" אחד; טלמטריה נכנסת נבדקת מול המיפוי שלו ומריצה את הפעולה המתאימה (edge-detected, לא חוזר על עצמו בכל פקט).

### קבצים חדשים
- `control/engine/bank_manager.py` — `BankStore` (CRUD + פרסיסטנס JSON ל-`banks/banks.json`, atomic write) ו-`eval_fixed_trigger()` שמממש את תנאי 6 הטריגרים הקבועים מול `speed`/`motionType`/`orientation`/`throw`/`catch`.

### קבצים ששונו
- `control/engine/engine.py` — `Engine.__init__` מקבל `send_dmx` ו-`banks_path`, יוצר `BankStore`. `on_telemetry` קורא ל-`_dispatch_bank_triggers` (edge-detection דרך אותו `_trigger_state` הקיים) → `_fire_bank_action` שמריץ את פעולת ה-Bank Timeline דרך `_fire_event()` הקיים (אין נתיב ביצוע נפרד — פעולת Bank היא בדיוק אותו פורמט `timelines` של Number event). נוסף `device == 'dmx'` ל-`_execute_step`.
- `control/server/app.py` — נוסף `_send_dmx` ל-wiring הראשי, ו-REST API: `GET/POST /api/banks`, `GET/PUT/DELETE /api/banks/<id>`, `POST /api/banks/<id>/activate`, `DELETE /api/banks/active`, `GET /api/banks/triggers`. אירועי `bank_triggered` (מה-Engine) ו-`bank_active_changed` יוצאים אוטומטית ל-WebSocket דרך אותו `_engine_event`/`socketio.emit` הקיימים.

### בדיקות
נבדק end-to-end ללא חומרה (`Engine` standalone, ללא Serial): יצירת Bank, מיפוי `toss`→Relay ו-`fast_spin`→DMX, הפעלה כ-Active Bank, שליחת טלמטריה מדומה — אושר edge-detection (לא נורה פעמיים על אותו מצב), דיספאץ' נכון של שתי הפעולות, ופרסיסטנס תקין (טעינה מחדש של `BankStore` מהדיסק משחזרת state). לא נבדק על חומרה אמיתית — אין UI עדיין לבנות Banks (ראה `bank-manager-ui-001`, תלוי במשימה הזו).

## [2026-07-19] דוח בדיקות: כיבוי LED לא יציב ב-M2-1 → 3 גורמי שורש + OTA מהימן + בורר אפקטים ב-Control

### תקציר
המשתמש דיווח שב-M2-1 (`onboarding.html`) הסטאף לא כבה, "כנראה התנגשות עם פקודות אחרות". בפועל נמצאו **שלושה** גורמי שורש עצמאיים, שכל אחד מהם לבדו הספיק לשבור את ההתנהגות — תוקנו כולם, אומתו על חומרה אמיתית (Master S3 `AD44`, Slave C3 `028C`), כולל תרחיש התנועה המקורי (הזזת הסטאף בזמן שהוא אמור להיות כבוי/מציג אפקט).

### גורם שורש 1 — `CMD_LED_OFF` לא היה מצב משלו ב-firmware
`firmware/staff/src/main.cpp`: `CMD_LED_OFF` רק איפס `cmdOverride=false` — בדיוק אותו מצב שמייצג "אין פקודה, עקוב אחרי ה-IMU". תוצאה: המאסטר עצמו חזר להדליק צבע לפי זווית (`LedManager::tilt`) בכל מחזור טלמטריה, וה-`SyncPacket` לסלייב חזר לשדר `CMD_LED_TILT` ברציפות — הסלייב מעולם לא קיבל OFF אמיתי, והמאסטר "נדלק בחזרה" בכל תזוזה.

**תיקון:** נוסף דגל נפרד `offActive` (מובחן מ"אין override"). כשהוא פעיל: המאסטר מציג `LedManager::off()` בכל מחזור (לא `tilt`), והסנכרון לסלייב משדר `CMD_LED_OFF` ברציפות (לא `CMD_LED_TILT`). מתאפס אוטומטית אם ה-Hub מתנתק (למצב אוטונומי).

### גורם שורש 2 — שארית קוד DMX-mirror יצרה עומס רדיו וטרפה sync packets
בכל מחזור טלמטריה (50ms) המאסטר שלח `sendTelemetry` + `sendSyncPacket`, ואחת ל-3 מחזורים גם `sendDMXCommand` (mirroring אוטומטי לצבע ה-LED, שארית מבדיקת DMX קודמת) — עד 3 קריאות `esp_now_send()` צפופות באותו tick. זה תאם בדיוק את הדיווח "הסלייב לא נכבה בכלל, וכשמזיזים את המאסטר הוא נדלק בחזרה" — עומס הרדיו גרם לאובדן sync packets לסלייב.

**תיקון:** הוסר לגמרי בלוק ה-DMX-mirroring מהלולאה החמה של המאסטר ב-`main.cpp`. תשתית `DMXCommand`/`sendDMXCommand` נשארה ב-`EspNow.cpp/.h` לשימוש עתידי דרך ה-Hub (`/api/command/dmx`), רק לא מופעלת אוטומטית יותר.

### גורם שורש 3 — Number דמו טעון תמיד ב-engine דורס פקודות ידניות
`numbers/example.json` ("Staff Rotation Demo") טעון כברירת מחדל תמיד ב-engine (`NUMBER_PATH` דיפולטי ב-`app.py`), עם אירוע `speed > 2.0` → policy `INTERRUPT` ששולח **אדום → (1.2s) כחול → (2s) כבוי**. פקודות ידניות (`/api/command/staff` מ-`onboarding.html`/`index.html`) עוקפות את ה-`DeviceRegistry` לגמרי — ה-engine לא יודע שיש שליטה ידנית, ודורס אותה בכל תזוזה שחוצה את סף המהירות. זה ההסבר המדויק לדיווח המאוחר יותר: "כן, אבל אז הוא פתאום עושה אדום, כחול ונכבה — בלי קשר למה שפקדתי".

**תיקון:** נוסף מנגנון "נעילת reactivity" לשני העמודים (`onboarding.html`, `index.html`) — בכניסה לעמוד מוחלף ה-Number הפעיל ל-`numbers/stress-test.json` (ריק, 0 events) דרך `/api/number/load`, וב-`beforeunload` מוחזר ה-Number המקורי (`example.json`) כדי לא לשבור את הדמו החי בהקשרים אחרים.

### תוספת — יכולת חדשה: חזרה מפורשת ל"זווית→צבע" (ברירת המחדל)
לפי בקשת המשתמש להוסיף בורר "מצבי אפקטים" לעמוד Control, בדיקה חשפה שלא הייתה שום דרך "לצאת" בחזרה למצב הריאקטיבי המקורי (זווית→hue רציף) אחרי ששולחת פקודה אחרת — `CMD_LED_TILT` היה מתועד כ"sync packets only" ולא טופל בכלל ב-switch של פקודות נכנסות.

**תיקון:** נוסף `case CMD_LED_TILT` ב-`main.cpp` שמנקה את כל דגלי ה-override (כולל `offActive`) וחוזר למצב ברירת המחדל.

### תוספת — Effect switcher ב-Control (`control/ui/index.html`)
נוסף בורר "Effect" לפאנל Staff LEDs עם 6 המצבים האמיתיים שהקושחה תומכת בהם: Solid / Sparkle / Flame / Rainbow / Vertical / Angle→Color (auto). שדות צבע/בהירות מוצגים/מוסתרים דינמית לפי רלוונטיות (ל-Sparkle השדה מתויג "Density" — זה מה שהוא בפועל בפרוטוקול), ונוסף מקרא קצר מתחת לבורר. תוקן באג ריצה שנתפס תוך כדי בדיקה חיה בדפדפן: `onEffectChange()` נקרא לפני שה-`const` שהוא תלוי בהם הוגדרו (temporal dead zone) — הוזזה קריאת האתחול לסוף ה-script.

### תוספת — OTA הפך לאמין (לא רק USB)
המשתמש ביקש יכולת OTA קבועה כדי לא להיות תלוי בפירוק/חיבור USB בכל פעם. אותרו ותוקנו שני חסמים:
1. **`control/server/app.py`**: קריאות ה-subprocess ל-`pio` (build + OTA flash) השתמשו בשם `'pio'` בלבד — לא נמצא ב-PATH של תהליך השרת (רץ מחוץ ל-shell אינטראקטיבי). נוסף `PIO_BIN = shutil.which('pio') or os.path.expanduser('~/.platformio/penv/bin/pio')`.
2. **מרוץ תזמון אמיתי**: `firmware/staff/src/main.cpp` מכבה WiFi אוטומטית אחרי חוסר-פעילות (`WIFI_AUTO_OFF_MS`, היה 2 דק') כדי להגן על ESP-NOW. זמן ה-build לבדו (~17-20 שניות) יכול לצרוך מספיק מהחלון שה-timeout יפוג בדיוק כש-`espota` מנסה להתחבר (`Host Not Found`) — נצפה בפועל בניסיון OTA ראשון. **תיקון:** הועלה ל-5 דק', ונוספו `ArduinoOTA.onStart`/`onProgress` שמאפסים את הטיימר בכל pulse של transfer פעיל — כך timeout לא יכול לקטוע העברה שכבר בעיצומה.

### אומת על חומרה אמיתית (לא סימולציה)
- זוהו הבקרים הפיזיים בבטחה לפני צריבה (`esptool chip_id`, לא הורס): `AD44`=ESP32-**S3**=Master, `028C`=ESP32-**C3**=Slave.
- שני הבקרים נצרבו מחדש דרך USB עם כל התיקונים (role נשמר תקין מ-NVS).
- **אישור משתמש ישיר**: "שניהם כבויים ולא מגיבים לתנועות של המכשיר" — התסמין המקורי נפתר.
- **מחזור OTA מלא הצליח** מקצה לקצה (WiFi ON → build כולל התיקונים → `espota` upload → reboot) — 40 שניות, ללא כשל timing.
- **אימות ויזואלי בדפדפן** (`claude-in-chrome`) על ה-Effect switcher: Solid/Flame/Sparkle/Angle→Color נבדקו בפועל מול השרת החי, כולל שליחה אמיתית ל-`AD44` ואישור חוסר שגיאות קונסולה.

### תקלות סביבה שנתקלנו בהן (לא באגי קוד — לתיעוד בלבד)
- ה-Hub חובר בטעות לפורט ה-USB **הנטיבי** שלו (OTG) במקום פורט ה-**UART/COM** (דרך שבב CH340) — קושחת `env:hub` לא מוגדרת עם `ARDUINO_USB_CDC_ON_BOOT`, כך שתעבורת ה-`Serial` בפועל יוצאת רק דרך ה-UART הפיזי. אחרי חיבור מחדש לפורט הנכון, הכל חזר לתפקד.
- אחרי כמה מחזורי WiFi/reset רצופים בזמן קצר, קישור ה-ESP-NOW בין ה-Hub לסטאף "נתקע" ולא חזר לבד — נפתר ע"י power-cycle פיזי אמיתי (לא רק reset תוכנתי).

### קבצים
- `firmware/staff/src/main.cpp` — `offActive`, הסרת DMX-mirror, `case CMD_LED_TILT`, `WIFI_AUTO_OFF_MS`, `ArduinoOTA.onStart/onProgress`.
- `control/server/app.py` — `PIO_BIN`.
- `control/ui/onboarding.html`, `control/ui/index.html` — engine reactivity lock; `index.html` גם Effect switcher + מקרא.

## [2026-07-19] תיקון קריטי: DMX לא עונה ל-discover + שליטה ידנית ב-DMX בממשק

### הבאג האמיתי (לא מה שחשבתי בהתחלה)
בדיקה ראשונית (הזזת `esp_now_send()` מחוץ ל-recv callback) לא פתרה את הבעיה. חיברתי סריאל ישירות ל-DMX (`/dev/cu.usbmodem142201`, מחובר גם ל-USB בנוסף ל-ESP-NOW) ואישרתי שהוא **חי ומקבל DMXCommand בזמן אמת** ברציפות (מהשידור העצמאי של ה-Master ל-DMX) — כלומר קליטה תקינה לגמרי, אז זה לא בעיית ערוץ/GROUP_ID/הספק.

**הגורם האמיתי**: `firmware/dmx/src/EspNow.cpp` — `EspNow::init()` **מעולם לא רשם peer לכתובת ה-broadcast**. קליטת broadcast לא דורשת peer רשום, אבל **שליחה** (`esp_now_send`) כן. `sendIdentity()` הוא המקום היחיד שה-DMX אי-פעם שולח (הוא לא שולח שום דבר אחר מיוזמתו) — ולכן נכשל בשקט (`ESP_ERR_ESPNOW_NOT_FOUND`) בכל קריאה, מאז ומתמיד.

### תיקון
- `firmware/dmx/src/EspNow.cpp` — נוסף `esp_now_add_peer()` לכתובת ה-broadcast ב-`init()`, זהה לדפוס הקיים ב-`firmware/hub/src/EspNow.cpp`.
- (נשאר גם התיקון הראשון כשיפור תקינות: `sendIdentity()` לא נקרא יותר ישירות מתוך ה-recv callback — נדחה ל-`EspNow::pollDiscover()` שנקרא מ-`loop()` דרך flag, לפי best-practice של ESP-NOW.)
- נבנה (`pio run`) וצרב (`pio run -t upload --upload-port /dev/cu.usbmodem142201`) ישירות דרך USB.

### אומת על חומרה אמיתית
- `POST /api/discover` אחרי הצריבה: DMX (`AD50`, role `dmx`, FW `v1.1`) מופיע כעת בתגובות, לצד Master/Slave.
- `POST /api/command/dmx` (endpoint חדש, ראה למטה) נבדק מקצה לקצה — פקודה ידנית (`addr=1 w=0 r=0 g=255 b=0`) נקלטה ונרשמה בלוג הסריאל של ה-DMX בזמן אמת.

### שליטה ידנית ב-DMX בממשק (החלפת ה-WRGB הישן)
- `control/server/app.py` — נוסף `POST /api/command/dmx` (`targetAddr, w, r, g, b`) → `proto.pack_dmx_command`.
- `control/ui/index.html` — פאנל "WRGB Lights" (PWM) **הוחלף** בפאנל "DMX512 Lights": שדה כתובת DMX התחלתית (ברירת מחדל 1) + 4 סליידרים W/R/G/B + Set/Off. תואם בדיוק למה שהקושחה כותבת בפועל: 4 ערוצים רצופים W,R,G,B מתחילת הכתובת (`firmware/dmx/src/main.cpp`).

### מגבלה ידועה — לא נפתרה, בכוונה
פרופיל הערוצים של **הפאנל הפיזי** (כמה ערוצים הוא תופס, ובאיזה סדר) לא ניתן לאימות מהקוד — DMX512 הוא חד-כיווני (controller→פנס, אין ערוץ חזרה). הקוד מניח 4ch W,R,G,B; אם הפאנל בפועל שונה (למשל דימר לפני הצבע, סדר צבעים אחר, ערוצי strobe/mode נוספים), זה שינוי ב-`main.cpp` שדורש בדיקה מול ה-DIP switches/תפריט של הפנס עצמו — לא נבדק בסשן הזה.

### הערה נוספת
בזמן הבדיקה נצפה שה-Master משדר DMXCommand ברצף גבוה יחסית (מיפוי צבע חי מזווית ה-IMU) — פקודה ידנית מה-Dashboard יכולה להידרס מהר ע"י השידור העצמאי הזה. לא טופל — אין עדיין מנגנון "מי גובר" בין שליטה ידנית לשידור אוטונומי של ה-Master.

### קבצים
- `firmware/dmx/src/EspNow.cpp`, `firmware/dmx/include/EspNow.h`, `firmware/dmx/src/main.cpp`.
- `control/server/app.py`, `control/ui/index.html`.

## [2026-07-19] דיבוג: DMX/Slave לא מופיעים ב-Network Dashboard

### מה בוצע
המשתמש דיווח שהחומרה כולה מחוברת אבל DMX וה-Slave לא מופיעים ב-`dashboard.html`. אבחון:
- `dashboard.html` (וכל שאר הדפים המוגשים) מציגים מכשירים רק דרך `_devices` בזיכרון בשרת, שמתמלא רק ע"י (א) מכשירים ששולחים טלמטריה מיוזמתם, או (ב) מענה ל-`MSG_DISCOVER` (`POST /api/discover`).
- **DMX**: מכשיר פסיבי — לא שולח שום דבר מיוזמתו (`firmware/dmx/src/EspNow.cpp`), עונה רק ל-discover.
- **Slave**: לפי `firmware/staff/src/main.cpp:137` (`if (g_txEnabled) { ... sendTelemetry ... }`) — ה-Slave מוגדר `g_txEnabled=false` ולכן **לא שולח StaffTelemetry בכלל, בכוונה** (Rx-only, מקבל רק SyncPacket מה-Master).
- הכפתור שהפעיל discover בעבר היה ב-`flasher.html`, שכבר לא מוגש (route לא רשום מאז 2026-06-08) — לא נסיגה בקוד החדש, פונקציונליות שחסרה מהמעבר.

### תיקון
נוסף כפתור **"🔍 גלה מכשירים"** ל-`control/ui/dashboard.html` (ליד "מצב מכשירים") שקורא ל-`POST /api/discover` (timeout 2.5s) ואז מרענן דרך `reconcile()` הקיים.

### אומת על חומרה אמיתית
`curl -X POST /api/discover` החזיר תגובות אמיתיות: Master (`AD44`) ו-Slave (`028C`), שני התפקידים `staff`. **DMX לא הגיב לסריקה** — צריך לבדוק פיזית (הזנת מתח / התאמת ערוץ ESP-NOW) בצד המשתמש, לא ניתן לאבחן מרחוק.

### הערה חשובה למשתמש
ה-Slave יופיע כ-`online:false` תוך כמה שניות אחרי כל סריקה — **זה תקין**, לא באג. אין לו heartbeat תקופתי (Rx-only לפי עיצוב), אז "online" ב-Dashboard מבוסס על טלמטריה חוזרת שהוא פשוט לא שולח.

### קבצים
- `control/ui/dashboard.html`.

## [2026-07-19] measure-ui-006 — בלוק "תוצאה מצופה" בכל שלב

### מה בוצע
נוסף `expected: {good, bad}` לכל שלב אופרטיבי ב-`onboarding.html` (M1b/c/d, M2-1/2/3, M3, M4, M5 — לא ל-M0/M1a שאין להם קריטריון עובר/נכשל), מוצג כבלוק ייחוס חדש (`.step-expected`) עם תגית ירוקה "מצופה" ותגית אדומה "דגל אדום". תוכן מבוסס על טבלאות ה"הכרעה" בסעיף 3 של המסמך, מותאם לתיקון הקודם (M1b/c/d לא נבדקים מול ±1g תיאורטי אלא מול "accY נשאר הציר הדומיננטי").

חשוב: זה טקסט ייחוס בלבד להצגה למבצע — אין שום חישוב/הערכה אוטומטית מול הנתונים החיים. לא סותר את כלל "אין ניתוח בזמן אמת בממשק".

### נבדק
- `node --check` על ה-JS.
- ספירת שלבים ב-`STEPS` נשארה 11 אחרי העריכה (לא נמחק/שוכפל שלב בטעות).
- `/onboarding.html` מוגש כראוי.

### קבצים
- `control/ui/onboarding.html`.

## [2026-07-19] measure-ui-005 — תיקון ציפיות M1b/c/d: אין הרכבה מיושרת בדיוק

### מה בוצע
המשתמש העיר שהחיישן מחובר ידנית על לוח שאינו מקובע בדיוק לזווית המוט — כלומר צפויה סטייה קלה בציר Y, ולכן אין לצפות ל-accY≈±1g תיאורטי; הכיול חייב להתבסס על מה שנמדד בפועל, לא הנחה. לפי בחירת המשתמש (Ask): הסטייה **לא** נמדדת עצמאית (אין זווית-מד מול הסטאף) — תוסק כולה מתוך הקריאות שנאספות ב-M1b/c/d.

עודכן `control/ui/onboarding.html`:
- **M1b**: הוסרה האזהרה "accY≈±1g אחרת עצור". הוגדר מחדש: הווקטור המלא (accX,accY,accZ) שנקלט באנך *הוא* נקודת הייחוס לכיול הסטייה, מנותח אחרי (offline). דגל אדום שנשאר: accY חייב עדיין להיות הציר **הדומיננטי בעליל** — לא בהכרח ±1g מדויק, אבל בבירור הגדול מ-accX/accZ; אחרת זה לא סטיית הרכבה קלה אלא ציר שגוי.
- **M1c**: accY צפוי להתהפך בסימן אך לא בהכרח באותו גודל מדויק כמו M1b — ההפרש עצמו הוא מידע.
- **M1d**: accY צפוי קטן מ-accX/accZ אך לא בהכרח 0 מדויק — השארית היא בדיוק נתון הכיול.

### נבדק
- `node --check` על ה-JS המוטמע.
- `/onboarding.html` מוגש כראוי (200) — קובץ סטטי, אין צורך באתחול שרת.

### קבצים
- `control/ui/onboarding.html`.

## [2026-07-19] measure-ui-004 — שליחת פקודת LED אוטומטית בשלבים רלוונטיים

### מה בוצע
המשתמש שאל אם הממשק שולח בפועל פקודת LED להאב בשלבים שדורשים לדים דלוקים/כבויים — התשובה הייתה לא (רק טקסט הוראה). נוסף `ledState` (`'off'`/`'full'`/ללא) ל-`STEPS` ב-`onboarding.html`, רק לשלבים שבהם המסמך **מפורש** לגבי מצב הלדים: M2-1 (off), M2-2/M2-3/M5 (full). שאר השלבים לא נוגעים במצב הלדים בכלל (אין ניחוש דרמטורגי).

- `applyLedState(state)` — `POST /api/command/staff` קיים (broadcast, ללא `targetId` → מגיע לכל ראשי הסטאף; לא נבנה מנגנון חדש). `full` = `CMD_LED_SOLID` לבן (255,255,255) בהירות 255; `off` = `CMD_LED_OFF`.
- נקרא אוטומטית ב-`goTo()` כשנכנסים לשלב עם `ledState` מוגדר.
- Badge בכרטיס השלב מציג את הפקודה שנשלחה + כפתור "שלח שוב" (למקרה שהחומרה לא הייתה מחוברת ברגע הכניסה לשלב).

### נבדק
- `node --check` על ה-JS.
- `curl` ל-`/api/command/staff` עם cmdType 0/1 — מחזיר `{"ok":true}` (ללא חומרה מחוברת, אין דרך לאמת קליטה בפועל על הסטאף).

### קבצים
- `control/ui/onboarding.html`.

## [2026-07-19] measure-ui-003 — שדה למדידה גיאומטרית ידנית (r) ב-M1a

### מה בוצע
ל-M1a לא היה שום מקום לתעד את r שנמדד בסרט מדידה — המשתמש העיר על כך. נוסף מנגנון "עובדות קמפיין" כללי (לא רק ל-r, ניתן להרחבה לשדות ידניים נוספים בעתיד):
- `control/server/app.py`: `GET/POST /api/measure/meta` — קורא/כותב `docs/measurements/_meta.json` (נפרד מקבצי ה-JSONL של ההקלטות עצמן; לא נכנס לרשימת `/api/measure/files` כי הסינון שם הוא לפי סיומת `.jsonl` בלבד). POST ממזג שדות (לא דורס), כל שדה נשמר עם `value` + `ts`.
- `control/ui/onboarding.html`: לשלב M1a נוסף `manualFields` (מבנה גנרי ב-STEPS) עם שדה `r_master_cm` — input + כפתור שמור, מציג את הערך והזמן שנשמרו. נטען פעם אחת ב-`loadMeta()` לפני הרינדור הראשון.

### נבדק
- מחזור מלא דרך השרת החי: GET ריק → POST → GET משקף את הערך שנשמר.
- אומת ש-`_meta.json` לא מופיע ב-`/api/measure/files`.
- נמחק ערך בדיקה (42.5) שנכתב תוך כדי הבדיקה — לא נתון אמיתי.

### קבצים
- `control/server/app.py`, `control/ui/onboarding.html`.

## [2026-07-19] measure-ui-002 — הרחבות: מחיקה/טעינת הקלטות + מדריך Onboarding

### מה בוצע
1. **מחיקה/טעינה ב-`measure.html`**: `GET /api/measure/view/<name>` (תצוגה גולמית, בלי הורדה) ו-`DELETE /api/measure/files/<name>` (עם הגנה מפני מחיקת קובץ שבהקלטה פעילה, ומפני path traversal) ב-`app.py`. שורת קובץ ברשימה קיבלה כפתורי "טען"/"מחק" לצד "הורדה", מחוברים ב-event delegation (לא inline onclick, כדי לא להישבר על שמות עם גרשיים).
2. **`control/ui/onboarding.html` חדש** — מדריך תפעולי צעד-אחר-צעד לפי `docs/SmartStaff_Measurement_Campaign_v2.md`: stepper עליון (M0→M1a-d→M2-1..3→M3→M4→M5) עם ✓ אוטומטי לשלבים שכבר יש להם קובץ מוקלט, כרטיס שלב עם מטרה/הוראות ממוספרות/משך יעד/אזהרות (למשל בדיקת סימן accY ב-M1b — "הכשל השקט המסוכן ביותר"), טיימר elapsed שמתאדם לירוק כשחוצה את משך היעד (10s ל-M1b-d, 60s ל-M2), וכפתור הקלטה מחובר לאותו backend כמו `measure.html` (תיוג שלב אוטומטי — לא טקסט חופשי, כדי למנוע טעויות הקלדה שיפגעו בניתוח מאוחר יותר). M0 מוצג כממצא סטטי (בלי כפתור הקלטה) עם החלטת ה-scope הנוכחית (Master בלבד) וממצא חוסר שדה ה-sequence.

### נבדק
- `py_compile` על `app.py`, `node --check` על ה-JS המוטמע בשני הדפים.
- מחזור מלא דרך השרת החי (לא test client): start→mark→stop→files→delete על `/api/measure/*` — תקין.
- path traversal על `DELETE .../../../etc/passwd` — נחסם (400).
- לא נבדק ויזואלית בדפדפן (הרחבת Chrome לא מחוברת בסשן) — השרת רץ ברקע לבדיקת המשתמש.

### קבצים
- `control/server/app.py`, `control/ui/measure.html`, `control/ui/onboarding.html` (חדש), `control/ui/nav.js`.

## [2026-07-19] measure-ui-001 — ממשק תפעול לקמפיין מדידות

### מה בוצע
נבנה `control/ui/measure.html` — ממשק תיעוד גולמי למדידות M1–M5 לפי `docs/SmartStaff_Measurement_Campaign_v2.md`. מבנה/רכיבי UI (כרטיס "MPU live DATA" עם raw מתקפל, כפתור הקלטה אדום, session raw log + export) בהשראת `Smart_Staff/Ver_Beta/BT_setup/dashboard/index.html` — לפי אישור מפורש של המשתמש להעתיק UI מהפרויקט הישן, בתנאי שה"מנוע" (זרימת הנתונים) יתאים לפרויקט הנוכחי. **חד-חיישני (Master בלבד)** בשלב זה — שילוב IMU של ה-Slave נדחה עד להחלטה לפי תוצאות המדידות (הנחיית המשתמש).

### שרת — `control/server/app.py`
- מצב הקלטה גלובלי בזיכרון (`_recording`) + `_record_frame()` שמצורף ל-`on_telemetry()` הקיים — כותב כל `staff_telemetry` שמגיע בזמן הקלטה כ-JSONL גולמי (`t_arrival` + הפריים כמו שהתקבל, ללא עיבוד).
- Endpoints חדשים: `POST /api/measure/start` (`{stage}` → פותח קובץ `docs/measurements/<ts>_<stage>.jsonl`), `POST /api/measure/mark` (מזריק marker, למשל "0°"), `POST /api/measure/stop`, `GET /api/measure/status`, `GET /api/measure/files`, `GET /api/measure/download/<name>`.
- נתיב `/measure.html` נרשם במפורש (תואם לדפוס `dashboard.html` — הגשת `control/ui/` הכללית מושבתת מאז 2026-06-08).

### ממשק — `control/ui/measure.html` + `nav.js`
- כרטיס live: angle/speed/orientation + raw acc x/y/z, gyro x/y/z (משיכה ישירה מאירוע `telemetry` ב-Socket.IO — כולל שדות גולמיים שלא זמינים ב-`device_update`), badges throw/catch/impact/spin.
- כפתור "🧪 סימולציה" — מזין נתונים סינתטיים לתצוגה בצד הלקוח בלבד (לבדיקת הממשק בלי חומרה מחוברת); לא נוגע בהקלטה server-side.
- שליטת הקלטה: בורר שלב (M1a...M5 + חופשי), Start/Stop, כפתור סימון 0°, ספירת פריימים.
- פאנל בריאות חיבור: קצב חבילות, Δt ממוצע/מקסימלי בזמן אמת. **הערה גלויה בממשק**: אין שדה sequence ב-`StaffTelemetry` הנוכחי — אין מדד % אובדן אמיתי, רק פערי זמן הגעה (proxy).
- רשימת קבצי הקלטה + הורדה ישירה.

### נבדק
- `python3 -m py_compile` על `app.py` — עובר.
- הרצת השרת ללא חומרה (`SERIAL_PORT` לא קיים) — עולה נקי, `/measure.html` מחזיר 200.
- בדיקת in-process דרך `test_client` + קריאה ישירה ל-`on_telemetry()`: `start` → 5 פריימים מדומים → `mark` → `stop` → אומת תוכן קובץ ה-JSONL (session_start/telemetry×5/marker/session_end, כולל `count` נכון).
- `node --check` על ה-JS המוטמע — תחבירית תקינה.
- **לא נבדק בפועל בדפדפן** — הרחבת Chrome (`claude-in-chrome`) לא הייתה מחוברת בסשן זה. השרת הושאר רץ ברקע (`localhost:5000/measure.html`, לוג ב-`/tmp/magzimus_server.log`) לבדיקה ויזואלית ע"י המשתמש.

### קבצים
- `control/server/app.py`, `control/ui/measure.html` (חדש), `control/ui/nav.js`, `tasks.json`.

## [2026-07-16] DMX Controller — אינטגרציית ESP-NOW + סנכרון צבע חי מה-Staff

### מה בוצע
נבנה `firmware/dmx/` מחדש מבדיקת bring-up סטטית (rainbow fade קבוע בקוד) לבקר DMX מלא המקשיב ל-ESP-NOW, לפי `magzimus_network_mapping_report.md` (בהיקף מצומצם שסוכם: Hub↔DMX בלבד, ללא Autonomous Fallback מה-Staff עדיין).

### פרוטוקול חדש
- `MSG_CMD_DMX = 0x15`, `DMXCommand` (7 bytes: groupId, targetAddr uint16, w,r,g,b) — נוסף ל-`firmware/hub/include/Protocol.h`, `firmware/dmx/include/Protocol.h`, `firmware/staff/include/Protocol.h`, ו-`control/server/protocol.py` (`pack_dmx_command`, role `7: 'dmx'`).
- Hub: `case MSG_CMD_DMX` ב-`main.cpp` מעביר ל-ESP-NOW כמו שאר המכשירים.
- DMX Controller (`firmware/dmx/`): `EspNow.cpp` חדש (init/dequeue/discovery, תבנית זהה ל-`firmware/relay`), `main.cpp` נכתב מחדש — שומר את לוגיקת שידור ה-DMX המאומתת (`dmx_driver_install`/`dmx_set_pin`/40Hz loop), מחליף את הצבע הקבוע בקוד בעדכון dmxData מ-`DMXCommand` שהתקבל.

### תכונה: Staff Master משדר את הצבע שלו ישירות ל-DMX (ESP-NOW broadcast)
בנוסף לזרימה הרגילה (Mac→Hub→DMX), ה-**Master עצמו** משדר `DMXCommand` תואם לצבע ה-LED הפעיל שלו (tilt/vertical/solid — לא flame/rainbow/sparkle, שהם אפקטים דינמיים per-pixel בלי צבע ייצוגי אחד) ישירות ב-broadcast, באותו מנגנון שכבר קיים לשליחת `SyncPacket` לראש ה-Slave. עצמאי לגמרי מה-Hub.
- `firmware/staff/include/LedManager.h/.cpp` — נוסף `hueToRgb()` (משתמש באותה עקומת HSV כמו `tilt()`/`tiltFromHue()`, בלי לגעת ברצועת ה-LED) כדי לחשב במדויק את אותו צבע שה-Staff מציג.
- `EspNow::sendDMXCommand()` נוסף ל-Staff (broadcast, זהה למבנה `sendPWMCommand`).
- ב-`main.cpp`, מיד אחרי `sendSyncPacket`: תרגום (sc,sr,sg,sb) → RGB סופי, ושליחה כ-`DMXCommand` לכתובת `DMX_MIRROR_ADDR=1` (ב-`Config.h`). מוגבל ל-1/3 ממחזורי הטלמטריה (throttle) כדי לצמצם עומס רדיו מול ה-sync packet התדיר יותר.

### אומת על חומרה
- בקר S3 חדש (MAC `...ad:50`) נצרב כ-DMX Controller, עולה נקי (`DMX Controller ready ID:AD50 FW:v1.1`).
- שליחת פקודה ידנית (Mac→Hub→DMX) אושרה בלוג המכשיר (`DMXCommand recv: addr=1 w=255 r=255 g=0 b=0`) ובפועל על הפיקסצ'ר (אדום תואם ל-Staff).
- לאחר הפעלת השידור החי מה-Master: התקבלו עדכוני `DMXCommand` רציפים ומשתנים (תואמים לזווית) בלוג ה-DMX.
- אומת סופית ע"י המשתמש: DMX וה-Staff (Master+Slave) מוצגים מסונכרנים.
- הערה: תקלת חוסר-סנכרון חד-פעמית בין Master↔Slave (לא קשורה ל-DMX) נפתרה ע"י איתחול פיזי של ה-Slave — כנראה סטייט תקוע משרשרת בדיקות ה-OTA הקודמת, לא רגרסיה מהשינוי הזה.

### קבצים
- `firmware/dmx/include/{Config,Protocol,EspNow}.h`, `firmware/dmx/src/{main,EspNow}.cpp`, `firmware/dmx/platformio.ini` (נוסף `GROUP_ID`).
- `firmware/hub/include/Protocol.h`, `firmware/hub/src/main.cpp`.
- `firmware/staff/include/{Protocol,EspNow,LedManager,Config}.h`, `firmware/staff/src/{EspNow,LedManager,main}.cpp`.
- `control/server/protocol.py`.

## [2026-07-16] אבחון ותיקון תקשורת Hub↔Staff + OTA עצמאי

### מה בוצע
אובחנה ותוקנה שרשרת תקלות שמנעה כל תקשורת Hub↔Staff↔Mac, ולאחר מכן הוקם מנגנון OTA שלא תלוי ברשת WiFi חיצונית.

### באגים שנמצאו ותוקנו
1. **Hub לא עולה בכלל (קריטי)** — `firmware/hub/platformio.ini`: `env:hub` הגדיר `ARDUINO_USB_CDC_ON_BOOT=1`, שמנתב את ה-`Serial` ל-USB הנטיבי של השבב. בפועל ה-Hub מחובר דרך פורט COM (UART פיזי חיצוני), לא USB נטיבי — כל קריאת `Serial.print` נתקעה לנצח מחכה לחיבור host שלא קיים. הוסרו הדגלים; `Serial` חוזר ל-UART0 הפיזי.
2. **התנגשות ערוצי WiFi/ESP-NOW בזמן OTA** — כשה-Staff מתחבר ל-AP חיצוני (רשת הבית) לצורך OTA, הרדיו נועל על ערוץ ה-AP וקורס את ESP-NOW (קבוע לערוץ 1), כולל הפקודה המרוחקת לכיבוי ה-WiFi בעצמה. **פתרון**: ה-Hub מקים כעת SoftAP קבוע משלו (`AP_SSID="MagHub"`, סיסמה `magzimus`) על ערוץ 1 (`firmware/hub/src/EspNow.cpp`, `WiFi.softAP(...)`), כך שה-Staff מתחבר אליו במקום לראוטר חיצוני — ללא התנגשות ערוצים בכלל.
3. **`WiFi.persistent(false)`** נוסף ל-`firmware/staff/src/main.cpp` (אחרי `EspNow::init()`) כדי שהדרייבר לא ישמור/ינסה להתחבר מחדש ל-flash בין אתחולים.

### אומת על חומרה
- Hub מדפיס `"Hub ready"` ומעביר טלמטריית Staff תקינה ל-Mac (161 חבילות תוך 8 שניות, ~20Hz).
- שני ראשי ה-Staff (Master S3 `AD44`, Slave C3 `028C`) מזהים את ה-Hub הדדית (`"Hub restored — following commands"`).
- מחזור WiFi ON→OTA-ready→WiFi OFF מלא נבדק על ה-Master: מתחבר ל-`MagHub` (`192.168.4.3`), **0 שגיאות ESP-NOW**, פקודת כיבוי מרוחקת מגיעה ומבוצעת (`"WiFi OFF"`).
- דחיפת OTA בפועל (`pio run -e staff-ota -t upload`) עדיין **לא הצליחה** במלואה (נכשלה בשלב ה-invitation UDP) — טרם אובחן הגורם; ייתכן שדורש שה-Mac יתחבר לרשת `MagHub` בפועל בזמן הדחיפה.

### שינויים בקוד
- `firmware/hub/platformio.ini` — הוסרו `ARDUINO_USB_MODE`/`ARDUINO_USB_CDC_ON_BOOT` מ-`env:hub`.
- `firmware/hub/include/Config.h` — נוסף `AP_SSID`/`AP_PASSWORD`.
- `firmware/hub/src/EspNow.cpp` — `WiFi.mode(WIFI_AP_STA)` + `WiFi.softAP(...)` בערוץ ESP-NOW.
- `firmware/staff/src/main.cpp` — `WiFi.persistent(false)`.
- `firmware/wifi_credentials.ini` — `WIFI_SSID`/`WIFI_PASSWORD` עודכנו ל-`MagHub`/`magzimus` (AP של ה-Hub, לא רשת בית).

### הערה
כלי הבדיקה שלי (`pyserial` מותקן ad-hoc) הניב כמה תוצאות שווא של "המכשיר תקוע" באמצע העבודה — התברר שזו תקלת כלי בדיקה (פתיחת חיבור חדש גורמת ל-reset של הבקר; לפעמים גם עם `dtr=False`), לא תקלת קושחה. אומת מחדש עם `cat` על הפורט הגולמי, ובהמשך עם חיבור serial יחיד ומתמשך (פתיחה פעם אחת, שליחה+האזנה על אותו חיבור).

### עדכון — הפתרון הסופי שנדרש (בהמשך אותו יום)
המשתמש ציין אילוץ: **ה-Mac חייב להישאר מחובר לרשת הבית ("oshri") ולא לעבור לרשת AP נפרדת של ה-Hub.** בנוסף התגלה שרשת "oshri" עצמה dual-band — ה-Mac מחובר אליה ב-5GHz (ערוץ 44), שבכלל לא רלוונטי ל-ESP32 (2.4GHz בלבד); הערוץ הרלוונטי הוא ה-2.4GHz של אותו ראוטר, שלא היה ידוע מראש.

**הפתרון שהוחלף:** במקום SoftAP עצמאי על ה-Hub (`MagHub`), ה-**Hub עצמו מצטרף זמנית לאותה רשת ("oshri") כמו ה-Staff** בזמן חלון ה-OTA — כך שני הצדדים נוחתים על אותו ערוץ אמיתי (מה שהראוטר של הבית מקצה), וה-ESP-NOW חוזר לעבוד ביניהם, כל זאת בלי שה-Mac יזיז את החיבור שלו בכלל.

- `firmware/wifi_credentials.ini` הוחזר ל-`oshri`/הסיסמה האמיתית (לא `MagHub`).
- `firmware/hub/platformio.ini` — נוסף `extra_configs = ../wifi_credentials.ini` כדי שגם ה-Hub יקבל את פרטי הרשת.
- `firmware/hub/include/Config.h` — הוסרו `AP_SSID`/`AP_PASSWORD` (לא בשימוש יותר).
- `firmware/hub/src/EspNow.cpp` — הוחזר ל-`WIFI_STA` פשוט (בלי SoftAP); נוספו `EspNow::wifiJoin()`/`wifiLeave()` — ה-Hub מצטרף/עוזב את `oshri` בהתאם.
- `firmware/hub/include/EspNow.h` — הוצהרו `wifiJoin()`/`wifiLeave()`.
- `firmware/hub/src/main.cpp` — טיפול ב-`MSG_WIFI_CTRL`: קודם מעביר את הפקודה ל-Staff דרך ESP-NOW (כשעדיין על ערוץ 1), *ואז* קורא ל-`wifiJoin()`/`wifiLeave()` על ה-Hub עצמו.

**אומת סופית על חומרה:**
- Hub הצטרף ל-`oshri` בהצלחה: `channel:11  ip:192.168.0.112`. Staff Master קיבל `ip:192.168.0.109` על אותה רשת.
- יש רעש זמני של שגיאות ESP-NOW בזמן שהשניים מתחברים (לא בו-זמנית) — לא נמנע לגמרי, אבל חולף לבד ברגע ששניהם מסונכרנים.
- **בוצעה דחיפת OTA אמיתית** (`pio run -e staff-ota -t upload --upload-port 192.168.0.109`) בזמן שה-Mac נשאר על `oshri` לכל אורך הדרך — **הצליחה במלואה** (`Result: OK`, `Success`, 54 שניות). הבקר עלה מחדש אחרי זה עם הקושחה החדשה, זיהוי IMU תקין, ותקשורת Hub↔Staff יציבה (0 שגיאות ESP-NOW).
- מחזור כיבוי (`WIFI_CTRL state=0`) גם אומת: ה-Hub מדפיס `"Hub left WiFi — back on ESP-NOW channel"` וחוזר לפעולה תקינה.

### סטטוס Slave (C3) — לא הושלם באותה ישיבה (וראה תיקון קריטי למטה)
Slave הצליח להתחבר ל-`oshri` (`WiFi ON host:staff-c3 ip:192.168.0.111`), אבל דחיפת ה-OTA בפועל נכשלה פעמיים: פעם אחת עם `Receive Failed` בצד המכשיר (מנגנון ה-auto-recovery המובנה עבד נכון וכיבה WiFi לבד), ופעם שנייה לא הצליח בכלל להתחבר מחדש ברצף הבדיקות המהיר.

### תיקון קריטי — `wifiDisable()` לא איפס את ערוץ ה-ESP-NOW
לאחר הבדיקות: המשתמש דיווח שה-Slave לא מציג אור בכלל, ושה-Master מציג כחול (צבע ה-fallback העצמאי) במקום פקודת LED_SOLID לבן ששלחתי. אבחון דרך ה-Serial של ה-Master חשף הצפה מתמדת של `ESPNOW: Peer channel is not equal to the home channel` — **המאסטר נשאר תקוע על הערוץ של רשת ה-WiFi החיצונית לצמיתות**, גם אחרי `"WiFi OFF"`.

**הסיבה:** `firmware/staff/src/main.cpp` — `wifiDisable()` קרא ל-`WiFi.disconnect(true)` אך **לא איפס בחזרה את ערוץ ה-ESP-NOW** (`esp_wifi_set_channel`), בניגוד למקבילה ב-Hub (`EspNow::wifiLeave()`) שכן עושה זאת. כתוצאה: אחרי כל מחזור OTA/WiFi, ה-Staff נשאר מנותק מה-Hub *וגם* מהראש השני לצמיתות עד איתחול פיזי — זה ההסבר לכל מה שנצפה (הכחול על המאסטר, הכיבוי על הסלייב, וכשל נסיונות ה-OTA החוזרים על ה-Slave לאחר מחזורים קודמים).

**התיקון:** נוסף `#include <esp_wifi.h>` ו-`esp_wifi_set_channel(ESPNOW_CHANNEL, WIFI_SECOND_CHAN_NONE);` בתוך `wifiDisable()`, מיד אחרי ה-`disconnect`.

**אומת על חומרה:** נבנה מחדש ונצרב לשני הראשים; שניהם עלו נקי (0 שגיאות ESP-NOW). המשתמש אישר: **שני הראשים עובדים ומסונכרנים**.

## [2026-07-13] dmx-bringup-001 — DMX Bring-Up - Hardware Verification & Transmission Test

### מה בוצע
- **PlatformIO Migration & Fixes:** הסבת קוד בדיקת שידור ה-DMX מטיוטת Arduino IDE לפרויקט PlatformIO תקני. תיקון לופ אתחולים (Boot Loop) בבקר על ידי הגדרה ידנית של נפח ה-Flash ל-4MB והגדרת ה-Partition Table ל-`min_spiffs.csv` ב-`platformio.ini` (מתאים לחומרת ה-ESP32-S3 SuperMini).
- **התאמת פינים חומרתית:** שינוי הגדרות הפינים בקוד ל-`TX_PIN = 2` (GPIO2) ו-`DMX_ENABLE_PIN = 1` (GPIO1) בהתאם לחיווט הפיזי המעודכן, כדי למנוע התנגשות UART בפין ה-TX הדיפולטיבי של מערכת ההפעלה (GPIO43).
- **צריבה ואימות (Flashing & Multimeter Verification):** צריבה מוצלחת של הקושחה לבקר בפורט `/dev/cu.usbmodem142301`.
  - מצב השידור (EN) נמדד יציב ב-2.36V.
  - שידור הנתונים (DI) נמדד יציב ותנודתי ב-0.87V (אות שידור DMX תקין ופעיל).
  - מוצאי DMX הדיפרנציאליים (A/B) תקינים ומשדרים הפרש מתחים בריא.
- **בדיקת פיקסצ'ר פיזי:** חיבור פנס DMX בכתובת 1. הפנס מגיב במדויק לצבעים שנשלחו בערוצים 1-10 (לבן, כחול, ירוק, אדום בהתאמה ל-dimmer וערוצי הצבע).

### שינויים בקוד
- **`firmware/dmx/platformio.ini`** (חדש) — הגדרות PlatformIO לפרויקט ה-DMX (ESP32-S3 DevKitC עם מחיצות 4MB).
- **`firmware/dmx/src/main.cpp`** (חדש) — קוד הבדיקה הראשי שהוסב.
- **`firmware/dmx/README.md`** (עודכן) — עדכון סטטוס הבדיקות והוראות ההפעלה עם פקודות ה-PlatformIO CLI וטבלת האימות המלאה.
- **`firmware/dmx/dmx_test/dmx_test.ino`** (נמחק) — קובץ ה-Arduino IDE הישן.

## [2026-06-29] lights-test-009 — End-to-End Lights System Verification

### מה בוצע
נכתב `tools/test_lights.py` — סוויטת בדיקות ל-Bridge + Light Nodes לפי `docs/magzimus-light-nodes-spec.md`: מבנה הפרוטוקול (`light_cmd_t`/`light_ack_t`), פרסור JSON (port פייתוני ל-`extractIntField`), לוגיקת ACK/Timeout (200ms), והתאמה סטטית של הקוד לספק (NODE_ID, PWM 1kHz/8-bit, GPIO low בבוט, no-ACK על פקודה כפולה, fire-and-forget). כולל גם בדיקת חיים (Serial + HTTP) שרצה אוטומטית אם יש Bridge מחובר.

### תוצאה
26/28 עברו. שני הכשלים הם בדיקות חיות (Serial + HTTP) שדורשות Bridge מחובר בפועל — לא היה מחובר בזמן הריצה (`credentials.h` עדיין עם SSID/password ריקים, כלומר ה-Bridge יעלה כרגע במצב AP-only). כל בדיקות ה-unit/static עברו, מאשרות ש-`lights-node-007` ו-`lights-bridge-008` תואמות לספק.

### שינויים בקוד
- **`tools/test_lights.py`** (חדש) — סוויטת בדיקות, כותבת דוח ל-`docs/LIGHTS_TEST_REPORT.md`.
- **`docs/LIGHTS_TEST_REPORT.md`** (חדש, auto-generated) — דוח תוצאות.

### הערה
לבדיקת Section 5/6 בפועל: לחבר Bridge דרך USB ול-`export BRIDGE_IP=<ip>` (במצב AP: `192.168.4.1`, SSID `MagLight`).

## [2026-06-29] lights-bridge-008 — Bridge Firmware Specification Alignment

### מה בוצע
יישור קושחת ה-Bridge (`firmware/bridge`) לפי `docs/magzimus-light-nodes-spec.md`: חיבור WiFi multi-network עם timeout ו-static IP לכל רשת, fallback ל-SoftAP, ממשק HTML מפושט (ללא frameworks), endpoint `/color`, ממשק Serial JSON תואם, וטיפול ב-ACK/timeout מ-ESP-NOW.

### שינויים בקוד
- **`firmware/bridge/include/credentials.h`** — נוסף `IPAddress ip/gateway/subnet` לכל רשת ב-`WifiNetwork` (לכל רשת ה-IP/gateway שלה).
- **`firmware/bridge/src/main.cpp`**:
  - לוגיקת boot: AP קבוע על channel 1 → ניסיון רשתות לפי `credentials.h` עם timeout מ-`Config.h` → `WiFi.config()` עם ה-IP הסטטי של הרשת שהתחברה → fallback להודעת "AP mode only" אם נכשל. הודעות `[BOOT]` ל-Serial בכל שלב.
  - HTML הוחלף לגרסה מפושטת בלי frameworks: שורת "הכל" + 4 שורות node, כל שורה סליידרים R/G/B/W וכפתור SEND, שולחת ל-`/color`.
  - Endpoint שונה מ-`/api/control` ל-`POST /color`, פרסור JSON (`target,r,g,b,w`) משותף בין HTTP ל-Serial דרך `dispatchColorJson()`.
  - נוסף ממשק Serial JSON: `pollSerial()` קורא שורה מסתיימת ב-`\n` ומפעיל את אותה לוגיקת dispatch כמו ה-HTTP.
  - נוסף `esp_now_register_recv_cb(onEspNowRecv)` — ה-callback רק שומר את ה-ACK האחרון ל-buffer (`s_hasAck`/`s_lastAck`), ועיבוד בפועל (`processAcks()`) קורה ב-`loop()` ומדפיס `[ACK] Node N: R=.. G=.. B=.. W=..`.
  - נוסף Async Timeout Tracker (`s_pending[1..4]`): כל שליחה מסמנת timer per-node (`trackSend()`), ו-`checkAckTimeouts()` ב-`loop()` מדפיס `[TIMEOUT] Node N` אם לא הגיע ACK תוך 200ms.

## [2026-06-29] lights-node-007 — Node Firmware Specification Alignment

### מה בוצע
יישור קושחת ה-Node (`firmware/pwm`, משמש כקושחת ה-C3 הפיזי במערכת הפנסים) לפי `docs/magzimus-light-nodes-spec.md`: `NODE_ID` קבוע בקומפיילציה, תדר PWM 1kHz, pull-low מיידי על ה-pins בעלייה, השוואת מצב (אין פעולה/ACK על פקודה כפולה), ושליחת `light_ack_t` ל-Bridge בשינוי מצב.

### שינויים בקוד
- **`firmware/pwm/include/Config.h`** — נוסף `NODE_ID` (1-4, ניתן ל-override דרך build_flags), `PWM_FREQ` שונה מ-5000 ל-1000Hz.
- **`firmware/pwm/platformio.ini`** — נוספו 4 environments (`node-c3-1`..`node-c3-4`) שמרחיבים את `env:pwm-c3` עם `NODE_ID` שונה לכל פנס.
- **`firmware/pwm/include/EspNow.h`** / **`src/EspNow.cpp`** — `deviceId` נקבע מ-`NODE_ID` (במקום byte אחרון של MAC); נוספה רישום peer ל-`BRIDGE_MAC` ופונקציית `sendAck()` ששולחת `light_ack_t` ל-Bridge.
- **`firmware/pwm/src/main.cpp`** — pull-low מיידי על 4 ה-pins בתחילת `setup()` (לפני LEDC/ESP-NOW); נוסף state מקומי (`curW/R/G/B`) ב-`loop()` — פקודה זהה למצב הנוכחי נדחית בלי applyPWM/ACK, פקודה שונה מעדכנת PWM ושולחת ACK.

## [2026-06-29] lights-proto-006 — Protocol & Shared Configuration Alignment

### מה בוצע
איחוד פרוטוקול ה-ESP-NOW בין Bridge ל-Node (מערכת הפנסים העצמאית, נפרדת מ-Hub/Staff) לשתי סטרוקטורות קבועות בגודל 5 בייט: `light_cmd_t` (Bridge→Node) ו-`light_ack_t` (Node→Bridge, יישומה בפועל ב-lights-node-007). יעד שידור broadcast שונה מ-`0xFF` ל-`0`.

### שינויים בקוד
- **`firmware/bridge/include/Protocol.h`** / **`firmware/pwm/include/Protocol.h`** — הוחלף `PWMCommand` (8 בייט) ב-`light_cmd_t` (5 בייט: `targetId,w,r,g,b`) ונוסף `light_ack_t` (5 בייט: `nodeId,w,r,g,b`).
- **`firmware/pwm/include/EspNow.h`**, **`firmware/pwm/src/EspNow.cpp`**, **`firmware/pwm/src/main.cpp`** — עדכון לשימוש ב-`light_cmd_t`; הוצאת מנגנון ה-fade (לא קיים יותר בפרוטוקול בן 5 הבייט — ימוקם מחדש כ-state machine ב-lights-node-007 אם יידרש).
- **`firmware/bridge/src/main.cpp`** — `handleControl()` ו-UI ה-HTML עודכנו ל-`light_cmd_t` (ללא `fadeMs`), וערך "כל הפנסים" שונה מ-255 ל-0.
- **`firmware/bridge/include/Config.h`** — `AP_SSID`/`AP_PASSWORD` עודכנו ל-`MagLight`/`magzimus`, נוסף `WIFI_NETWORK_TIMEOUT_MS`.
- **`firmware/bridge/include/credentials.h`** (חדש) — שלד טבלת רשתות WiFi (`WIFI_NETWORKS`) לניסיון STA לפני fallback ל-SoftAP; שימוש מלא ב-lights-bridge-008.

 נאמבר חדש — Staff Vertical Green/Blue (פריסט מקומי בקושחה)

### מה בוצע
נוסף נאמבר חדש: כשראש המאסטר של ה-Staff מצביע ישר למעלה (אנכי, `angle≈0°` ±20°) הוא דולק **ירוק**, ובכל זווית אחרת **כחול**. מעבר אנכי-מטה (`angle≈±180°`, "inverted") **לא** נחשב לאנכי בנאמבר הזה — בכוונה, לפי הנחיית המשתמש.

לוגיקת זווית→צבע **רצה מקומית בקושחת ה-Staff** כפריסט עצמאי (לפי ארכיטקטורת "אפקטים הם פריסטים על הבקרים בציוד הקצה") — אין צורך בלולאת חישוב חוזרת דרך ה-Mac/Engine; ה-Engine רק מפעיל את הפריסט פעם אחת בתחילת הנאמבר.

### שינויים בקוד
- **`firmware/staff/include/Protocol.h`** — נוסף `CMD_LED_VERTICAL = 7` (sync packets: `r`=0/1 flag).
- **`firmware/staff/include/Config.h`** — נוסף `LED_VERTICAL_GREEN_WINDOW_DEG = 20.0f`.
- **`firmware/staff/include/LedManager.h` / `LedManager.cpp`** — נוספו `vertical(angleDeg)` (מחשב ירוק/כחול מהזווית) ו-`verticalFromFlag(isVertical)` (רינדור ישיר מ-flag, לשימוש ה-slave).
- **`firmware/staff/src/main.cpp`** — נוסף `verticalActive` state, טיפול ב-`CMD_LED_VERTICAL` (master + slave sync דרך `SyncPacket`), ושילוב ברינדור האוטונומי וב-reset של מצבים מתחרים.
- **`control/engine/engine.py`** — נוסף `LED_VERTICAL` ל-`_execute_step` (שולח `cmdType=7`).
- **`numbers/staff-vertical-green.json`** — נאמבר חדש: אירוע `staff_telemetry` עם `condition: "True"` (יורה פעם אחת בעליית הנאמבר) ששולח `LED_VERTICAL` ל-Staff (broadcast, `targetId: 65535`).

### הערה
לא נצרב/נבדק על חומרה אמיתית — רק עריכת קוד ויצירת הנאמבר.

## [2026-06-08] השבתת ממשק הווב (Web UI)

הוסרה הגשת ה-UI מתוך `control/server/app.py`: בוטל ה-`static_folder`/`static_url_path` שהצביעו ל-`control/ui/`, והנתיב `/` מחזיר כעת JSON סטטוס במקום `index.html`. קבצי ה-UI (`control/ui/*.html`, `nav.js`, `shared.css`) נשארו על הדיסק לעיון עתידי, אך אינם מוגשים יותר. שאר ה-API (`/api/...`) והמנוע נשארו ללא שינוי.

## [2026-06-08] Trigger-Based Staff Angle Colors — Number Design & System Verification

### מספר חדש
- `numbers/staff-angle-colors.json` — מספר event-driven: Staff נדלק **ירוק** כש-`abs(angle) >= 20` ו-**אדום** כש-`abs(angle) < 20` (0°/180° = אנכי לפי מיפוי ה-pitch של הטלמטריה). שני אירועים (`evt-angle-green`/`evt-angle-red`) עם trigger מסוג `staff_telemetry` ו-Timeline `LED_SOLID` במדיניות `INTERRUPT`.

### באגים שנמצאו ותוקנו
1. **קונפליקט מבני 8-בייט (קריטי)** — `firmware/staff/src/EspNow.cpp`: `HubCommand` ו-`SyncPacket` שניהם 8 בייט, ולכן `SyncPacket` נופרס כ-`HubCommand` ונפסל ע"י בדיקת `targetId` — כל מנגנון הסנכרון Master↔Slave היה שבור. תוקן ע"י בדיקת `data[1] == MSG_SYNC` לפני ההשוואה הגנרית, והוסרה ענף כפול מת.
2. **"לחימה" על ה-LED אצל ה-Slave** — `firmware/staff/src/main.cpp`: רינדור LED מקומי לפי IMU רץ תמיד גם ב-slave mode, ודרס את הצבע המסונכרן מה-Master. נעטף ב-`if (!g_slaveMode)`.
3. **צבע LED_SOLID לא מועבר ב-sync** — `firmware/staff/src/main.cpp`: ה-Master שלח ב-`SyncPacket` r/g/b=0 עבור `CMD_LED_SOLID` (השדה הוזן רק עבור sparkle/tilt). נוסף `solidR/solidG/solidB` שנשמרים בעת קבלת `CMD_LED_SOLID`, ונשלחים כראוי ב-sync.
4. **Engine ללא edge-detection** — `control/engine/engine.py`: טריגרים מבוססי-תנאי (כמו `abs(angle) >= 20`) ירו על כל חבילת טלמטריה (~10/שנייה), מה שגרם להפעלות חוזרות/הבהוב. נוסף `_dispatch_trigger`/`_trigger_state` שמפעיל אירוע רק במעבר False→True (rising edge).

### צריבה ואימות
- שני המכשירים (Master S3 `AD44`, Slave C3 `028C`) נצרבו מחדש דרך USB ישיר עם הקושחה המתוקנת (תפקידים נשמרו ב-NVS).
- אומת Live על חומרה אמיתית: סיבוב המוט עובר בין אדום (אנכי) לירוק (מוטה) בזמן אמת, ה-edge-detection מונע ירי חוזר, ושני הראשים (Master+Slave) מציגים את אותו צבע במקביל — סנכרון תקין.

## [2026-06-07] Stress Test & Bug Fix Round

### Engine
- `control/engine/engine.py` — `_EVAL_CONSTS` dict: `vertical`, `horizontal`, `inverted`, `short`, `long`, `double`, `triple`, `press`, `release` מוגדרים כ-string values בתוך context ה-eval. מאפשר תנאים כמו `orientation == vertical` בלי quotes. נבדק: כל 28 tests עוברים.
- `control/engine/engine.py` — pedal_event trigger: עבר מ-field נפרד ל-eval עם fallback. אחיד עם שאר הטריגרים.

### API
- `control/server/app.py` — הוסף `import struct`.
- `control/server/app.py` — `cmd_staff`, `cmd_relay`, `cmd_pwm`: גלישת try/except ל-`struct.error`/`TypeError`/`ValueError`. קלט לא-int מחזיר 400 במקום 500.
- `control/server/app.py` — `accumulator_pulse`: `float(amount)` גלוי ב-try/except → 400 עם string.
- נבדק: 44/44 API tests עוברות.

### Protocol Tests
- `tools/test_protocol.py` Section 3: עדכון hex ל-25 bytes (StaffTelemetry v2) עם struct.pack. בדיקה אומתת flags.throw + orientation.
- נבדק: 19/20 (כישלון 1: פורט סידורי תפוס — חומרה).

### Node Editor (editor.html)
- **Bug קריטי תוקן**: `toggleFreeze(${node.id})` → `toggleFreeze('${node.id}')`. node.id הוא string ("n1") — ללא quotes JS מנסה לקרוא משתנה לא-מוגדר.
- **Bug חזותי תוקן**: `redrawEdges` — חישוב שגוי של מיקום port כשזום ≠ 1. תיקון: `toScreen(node.x, node.y).x + NW` (לא `toScreen(node.x + NW, ...)`).
- **Bug חזותי תוקן**: draft edge (בזמן גרירת חיבור) — אותה בעיה. תיקון: `cnO.x + portLocalX` (לא `toScreen(node.x + portLocalX, ...)`).
- **Bug לוגי תוקן**: `buildTrigger` לחיבור ישיר sensor_pedal → action: החזיר `'pedal_telemetry'` (לא קיים), עכשיו `'pedal_event'`.

### טסטים חדשים
- `tools/test_engine_edge.py` — 28 בדיקות: string conditions, numeric conditions, pedal/mic/staff cross-isolation, INTERRUPT/QUEUE/IGNORE, ShowTimer, Accumulator, malformed inputs.
- `tools/test_api.py` — 44 בדיקות: כל routes, path traversal security, input validation, no-engine graceful handling.

## [2026-06-07] df5c7bfb-6696 — Firmware Builder & Effect Bundling Module
`firmware/staff/include/EffectPresets.h` — קובץ preset חדש עם ערכי ברירת מחדל (flame hue/bright/sat, rainbow step, sparkle fade). ניתן לדריסה על ידי Builder לפני הידור.
`firmware/staff/src/LedManager.cpp` — flame/rainbow/sparkle משתמשים ב-PRESET_* constants במקום ערכים קשיחים.
`control/server/app.py` — נוספו: `_write_effect_presets()`, `POST /api/firmware/build` (pio run -e env, streaming via build_log/build_done WebSocket, staging .bin → firmware/builds/), `GET /api/firmware/builds` (רשימת builds מ-staging).
`control/ui/flasher.html` — קארד "Firmware Builder" חדש: בחירת firmware (8 envs), sliders לeffect presets (staff בלבד), כפתור Build, log terminal בזמן אמת, רשימת staged builds + Flash OTA.

## [2026-06-07] spec-test-001 — Staff Extended Telemetry (Section 10 ב-test_protocol.py)
`tools/test_protocol.py` — Section 10 חדש:
- unit tests: parse מחזיר כל מפתחות flags, דיקוד 0x05 (throw+spin_cw), כל ערכי orientation.
- live test: SerialBridge 5 שניות, מדפיס סטטיסטיקות flags בזמן אמת.
הערה: Staff מתחבר דרך ESP-NOW → Hub → Mac (לא USB ישיר).

## [2026-06-07] spec-test-006 — Node Editor Compiler Validation
`control/ui/editor.html` — validate() משופר:
- Frozen node support: `node.data.frozen` — frozen nodes מדולגים מ-validation ומ-active edges. opacity 0.4 בקנבס.
- toggleFreeze() + כפתור ❄/☁ בפאנל properties כל node.
- בדיקת payload > 64KB: JSON.stringify + TextEncoder, חוסם OTA אם גדול מדי.
- payload size מוצג ב-success message.

## [2026-06-07] spec-test-007 — Show Runner Transitions
`control/ui/planner.html` — selectNumber() עם transition indicator: badge מציג "⏳ טוען…" בזמן load, עובר ל-"▶ שם-הנאמבר" כשהשרת מאשר. goNext()/goBack() wraps around lineup. Pedal double/triple מחובר. SHOW MODE חוסם OTA ב-editor.

## [2026-06-07] spec-fw-001 — Staff Extended Telemetry (throw/catch/spin/orientation/impact)
`firmware/staff/include/Protocol.h` — הוסף 8 קבועי STAFF_FLAG_* + שדה `uint8_t flags` ל-StaffTelemetry (25 bytes).
`firmware/staff/include/Config.h` — נוספו pragmas: THROW_SPEED_MIN_RADS, FREE_FALL_THRESHOLD_G, CATCH_ACC_THRESHOLD_G, SPIN_SPEED_THRESHOLD, IMPACT_THRESHOLD_G, ORIENT_VERTICAL/INVERTED_DEG.
`firmware/staff/include/ImuManager.h` + `src/ImuManager.cpp` — state machine לזיהוי throw/catch (free-fall + speed), spin CW/CCW, orientation (vertical/horizontal/inverted), impact. שדה `flags` ב-ImuData.
`firmware/staff/src/main.cpp` — `pkt.flags = imu.flags` ב-telemetry assembly.
`firmware/hub/include/Protocol.h` — עדכון StaffTelemetry + STAFF_FLAG_* constants.

## [2026-06-07] spec-fw-002 — Progress Bar Firmware (ESP32-C3 + 100× WS2812B)
`firmware/progressbar/` — פרויקט PlatformIO חדש:
- `platformio.ini`: esp32-c3, FastLED dependency.
- `include/Config.h`: LED_PIN=8, NUM_LEDS=100, ESPNOW_CHANNEL=1.
- `include/Protocol.h`: ProgressCommand struct (9B), ROLE_PROGRESS_BAR=4.
- `src/main.cpp`: ESP-NOW receiver. Mode 0=progress fill (value 0-100 → LED count), Mode 1=solid color. Fade interpolation, 60 FPS render loop.

## [2026-06-07] spec-fw-003 — Microphone Firmware (ESP32-C3 + MAX9814)
`firmware/mic/` — פרויקט PlatformIO חדש:
- `platformio.ini`: esp32-c3, arduinoFFT dependency.
- `include/Config.h`: MIC_ADC_PIN=0, SAMPLE_RATE=8000, FFT_WINDOW_SIZE=256, TELEMETRY_MS=50.
- `include/Protocol.h`: MicTelemetry struct (15B), ROLE_MIC=5.
- `src/main.cpp`: ADC sampling 8kHz, DC removal, RMS/peak normalized 0-1 (over 4095), ArduinoFFT לדומיננטי frequency, שליחת MicTelemetry כל 50ms.

## [2026-06-07] spec-fw-004 — Pedal Firmware (ESP32 + microswitch + LED)
`firmware/pedal/` — פרויקט PlatformIO חדש:
- `platformio.ini`: esp32dev.
- `include/Config.h`: BUTTON_PIN=5 (INPUT_PULLUP), SHORT=300ms, LONG=700ms, DOUBLE=400ms, TRIPLE=600ms, DEBOUNCE=20ms.
- `include/Protocol.h`: PedalEvent (4B), PedalEventType enum (SHORT/LONG/DOUBLE/TRIPLE/PRESS/RELEASE), NetStatusCommand, ROLE_PEDAL=6.
- `src/main.cpp`: Debounced FSM, tap counter לdouble/triple, sendEvent(), setLed() לפי NetStatusCommand (ירוק/צהוב/אדום).

## [2026-06-07] spec-proto-001 — Protocol extensions (protocol.py + serial_bridge.py + hub firmware)
`control/server/protocol.py` — עדכון מלא:
- StaffTelemetry struct: `'<BHffhhhhhhBB'` (25B), parse_staff_telemetry מחזיר flags/throw/catch/spin_cw/orientation/impact.
- parse_mic_telemetry (15B), parse_pedal_event (4B), parse_effect_list (variable).
- pack_progress_command, pack_net_status.
- קבועים: MSG_MIC_TELEMETRY=0x02, MSG_PEDAL_EVENT=0x03, MSG_CMD_PROGRESS=0x13, MSG_NET_STATUS=0x14, MSG_EFFECT_LIST=0x22.
`control/server/serial_bridge.py` — callbacks: on_mic_telemetry, on_pedal_event, on_effect_list. _dispatch מטפל בסוגי הודעות חדשים.
`firmware/hub/include/Protocol.h` — MicTelemetry, PedalEvent, ProgressCommand, NetStatusCommand, EffectListHeader, EffectEntry structs. SerialMsgType enum עדכון.
`firmware/hub/src/EspNow.cpp` — onRecv() מנתב MicTelemetry/PedalEvent/EffectList → Serial.
`firmware/hub/src/main.cpp` — cases: MSG_CMD_PROGRESS, MSG_NET_STATUS → EspNow::send.

## [2026-06-07] spec-proto-002 — Hub Dynamic Effect Discovery (MSG_EFFECT_LIST)
`firmware/staff/src/EspNow.cpp` — sendEffectList(): broadcast ב-boot, header (5B) + 6 EffectEntry (OFF/SOLID/SPARKLE/FLAME/RAINBOW/TILT).
`firmware/staff/src/main.cpp` — קריאה ל-sendEffectList() ב-setup().
`firmware/staff/include/EspNow.h` — הצהרת sendEffectList().
`control/server/app.py` — _effect_registry dict, on_effect_list callback, GET /api/effects route.

## [2026-06-07] spec-eng-001 — Engine new sensors (Mic, Pedal, Staff extended triggers)
`control/engine/engine.py` — on_mic_telemetry(), on_pedal_event() routing methods.
_check_trigger() תומך ב: 'mic_telemetry' (תנאי על rms/peak/frequency), 'pedal_event' (תנאי על eventType), 'staff_telemetry' מורחב עם throw/catch/spin_direction/orientation/impact.
_execute_step() תומך ב-progressbar device (PROGRESS_SET cmd).
set_event_callback(cb) לemission של events לממשק.

## [2026-06-07] spec-eng-002 — Engine ShowTimer + Accumulator
`control/engine/engine.py`:
- ShowTimer class: countdown thread, start()/stop(), on_tick/on_done callbacks, מפעיל cancel_all()+apply_all_idles() בהפעלה.
- Accumulator class: pulse(amount), reset(), _decay_loop() thread, on_scored/on_climax callbacks.
- show_timer_start/stop, accumulator_configure/pulse/reset/value.
`control/server/app.py` — routes: /api/showtimer/start, /api/showtimer/stop, /api/accumulator/configure, /api/accumulator/pulse, /api/accumulator/reset, /api/accumulator/value.

## [2026-06-07] spec-eng-003 — Engine IDLE state management
`control/engine/device_registry.py` — self._idles dict, set_idle(device, target_id, cmd), get_idle(), apply_all_idles(make_sender), cancel_all().
`control/engine/engine.py` — tl.on_done_callback → שליחת IDLE cmd אחרי סיום timeline. on_show_timer_done() קורא cancel_all()+apply_all_idles().

## [2026-06-07] spec-ui-001/002/003 — Node Editor (Canvas + Nodes + Compiler)
`control/ui/editor.html` — עורך Node Graph מלא ב-SVG vanilla:
- 10 node types: SENSOR, TRIGGER, COMBINE, EVENT, SEQUENCE, SHOW_TIMER, ACCUMULATOR, IDLE, COUNTER, NET_STATUS.
- Pan (Alt+drag/MMB), Zoom (wheel), port-based bezier wiring.
- Undo/Redo (Ctrl+Z/Y, 50 snapshots), autosave 1s debounce.
- Properties panel דינמי לכל node type. SEQUENCE עם inline step editor.
- Validation: SENSOR→COMBINE direct, multiple sources same priority.
- Compiler: קנבס → Number JSON format.
- OTA: save + /api/number/load. OTA button חסום עד validation נקי.

## [2026-06-07] spec-ui-004 — Show Runner (planner.html) — Lineup + Dashboard
`control/ui/planner.html` — מסך הפעלת מופע:
- Mode banner (SHOW MODE — אדום קבוע), confirmation modal לפני כניסה.
- Lineup: רשימת נאמברים ממוספרת עם click-to-activate.
- Telemetry bar: staff speed/angle, mic RMS/freq. Flags strip (throw/catch/impact/orientation/spin).
- ShowTimer card: duration input, Start/Stop, countdown חי.
- Accumulator card: progress bar, decay rate, configure/pulse/reset.
- Network health grid: per-device cards עם live/dead pips, stale detection 5s.
- Pedal: double→goNext(), triple→goBack(). SHOW MODE: editing disabled.

## [2026-06-01] Software Update & Network Configuration Interface (df5c7bfb-1191)
`control/ui/flasher.html` — דף OTA ורשת מלא עם MD3 light theme:
- גילוי מכשירים (ESP-NOW discover + WiFi per-device toggle)
- OTA Flash מקביל: בחירת env + target, streaming progress via WebSocket (`ota_log` / `ota_done`)
- Hub heartbeat pause control
- הוראות USB flash לכל הplatforms
`control/server/app.py` — נוספו: `/api/ota/flash` (parallel threading), `/api/ota/scan` (mDNS), `/api/numbers/list`, `/api/numbers/save`, `/api/numbers/get`

## [2026-06-01] Node-based Timeline and Event Editor (df5c7bfb-2292)
`control/ui/editor.html` — עורך Node Graph ב-SVG:
- Event Nodes (trigger type + condition)
- Timeline Block Nodes (device, target, policy, steps עם drag-and-drop GUI)
- חיבור nodes ע"י bezier edges (port → port)
- Properties panel מלא לכל node type
- שמירה לשרת (`/api/numbers/save`), Export JSON, טעינת קבצים קיימים
- JSON תואם לפורמט numbers/example.json

## [2026-06-01] Show Planner and Sidebar Navigation Module (df5c7bfb-3393)
`control/ui/planner.html` — לוח ניהול מופע:
- רשימת נאמברים (load מהשרת, refresh כל 10s)
- טעינת נאמבר לengine ע"י לחיצה
- Real-time telemetry strip (Device ID, Speed, Angle, Motion, RSSI)
- מחווני node status (Staff, Relay, PWM)
- Sidebar nav (`nav.js`) זמין בכל הדפים
`control/ui/shared.css` — MD3 light theme tokens + sidebar + כל ה-components
`control/ui/nav.js` — sidebar navigation injection משותף

## [2026-06-01] LED & WRGB Light Effect Designer Interface (df5c7bfb-4494)
`control/ui/effects.html` — מעצב אפקטים אינטראקטיבי:
- LED preview canvas (144 LEDs, 6×24 grid, serpentine mapping + virtual gap)
- 6 אפקטים: Solid, Rainbow, Sparkle, Flame, Pulse, Chase — עם animation loop 30+ FPS
- Color sliders (R/G/B/Brightness) עם live update
- WRGB preview + sliders + fade
- שליחה לשרת: `/api/command/staff` + `/api/command/pwm`
- Hover inspect: מציג צבע per-LED

## [2026-06-01] Multi-Node Timeline Show Composer (df5c7bfb-5595)
`control/ui/composer.html` — עורך ציר זמן רב-ערוצי:
- Tracks: Staff / Relay / PWM (ניתן להוספה דינמית)
- Canvas timeline עם ruler (0.5s grid), keyframe blocks (drag + resize)
- Transport: Play/Pause/Stop/Skip + scrub bar + playhead
- Modal עריכת keyframe (cmd, colors, duration, fade)
- Export JSON + שמירה לשרת (תואם numbers format)

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

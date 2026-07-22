# Effect Composer — הצעת אפיון לשדרוג

**Antigravity Project | Smart Staff Dashboard | v0.1 | מארס 2026**

> ⚠️ **סטטוס המסמך: הצעה, לא תוכנית מחייבת.**
> מסמך זה הוא הצעת שדרוג אדריכלי לשיקול הסוכן שמכיר את ארכיטקטורת המכשיר. אין כאן הנחיית ביצוע. כל החלטה — כולל דחייה, שינוי, או פיצול לשלבים — נשארת בידי הסוכן. במקומות שבהם נדרש מידע שרק הסוכן מחזיק, המסמך מסמן **Open Question** במקום להכתיב פתרון.

> 📌 **הקשר מקורי: פרויקט Smart Staff.** ההקשר שממנו נכתב המסמך הוא הפרויקט המקורי של ה‑Smart Staff. התייחסויות לקבצים ולמודולים ספציפיים (`motion_trainer.js`, `motion_model.js`, `effects_engine.js`, `presets.js`, `showPage()`, `trainPage`, וכו') הן **רפרנס המשכיות מהפרויקט המקורי** — הסוכן מכיר אותן ומכיר גם את הפרויקט החדש, ועליו למפות אותן לארכיטקטורה הנוכחית בפועל. אין להניח שהקבצים האלה קיימים כלשונם בפרויקט החדש; הם משמשים כאילוסטרציה של הדפוס (Zero‑Touch, wrap‑hook, IndexedDB), לא כמצב עדכני.

---

## 0. הקשר

ה‑Dashboard הקיים מגביל את האמן לכמה פריסטים מוגדרים‑מראש, עם חופש יצירתי מועט. ההצעה: להוסיף שכבת **חיבור אפקטים (Effect Composer)** שמאפשרת לעצב אפקטים מלאים — פאטרן, צבעים, פרמטרים — ולשמור אותם בספרייה אישית, בלי לרדת לרמת single‑pixel או תכנות.

הסקופ של המסמך הזה הוא **הגדרת האפקט בלבד** (שלב 1). קשירת טלמטריית ה‑IMU לפרמטרים (שלב 2) אינה בסקופ, אבל הסכמה המוצעת בנויה כך שכל פרמטר יוכל להפוך ל‑binding בשלב 2 בלי שכתוב.

**עקרון Zero‑Touch נשמר.** בדיוק כמו `motion_trainer.js` ו‑`motion_model.js`: מודולים חדשים עצמאיים, wrap‑hooks בלבד, אפס נגיעה ב‑`effects_engine.js` / `presets.js` / Comm / State.

---

## 1. רקע מחקרי — הקונבנציות שההצעה נשענת עליהן

ההצעה מסתמכת על ארבע מערכות ייחוס מוכרות בתחום. לא כדי לחקות — כדי לאמץ מוסכמות שכבר הוכחו.

| מערכת | מה לוקחים ממנה |
|---|---|
| **WLED** | מודל פרמטרים אוניברסלי (speed, intensity, עד 5 סליידרים + 3 checkboxes, 3 צבעים, palette). ומעל הכל: **מטא‑דאטה שמסתירה דינמית בקרות שהאפקט הנוכחי לא משתמש בהן** — הפתרון ל"מקיף אך לא מציף". |
| **Pixelblaze** | כל אפקט **מכריז על הבקרות של עצמו**; ה‑UI נבנה מהצהרת הפרמטרים. `pixel maps` שמפשיטים את הפריסה הפיזית — אפקט אחד עובד על כל סידור לדים. |
| **FastLED** | אוצר הפרימיטיבים: palettes, HSV, רעש Perlin (`inoise8`), אוסילטורים (`beatsin8`), `blend`, `fill_gradient`, easing. הלבנים שמהן בונים את משפחת הפאטרנים. |
| **LtComposer (המתחרה)** | מבוסס **timeline / תוכן מבושל מראש**. הבידול של Smart Staff הוא **תגובתיות** — ולכן הכלי כאן צריך להיות **פרמטרי/גנרטיבי, לא ציר‑זמן.** זו החלטת עמדה, לא רק טכנית. |

---

## 2. מודל הליבה המוצע

### 2.1 מודל קומפוזיציוני

אפקט = **מקור צבע** × **אנימטור** × **מודיפייררים**. כל רכיב מכריז על סכמת הפרמטרים שלו, וה‑UI מרנדר רק את הבקרות הרלוונטיות לאפקט הנבחר (שילוב של metadata‑hiding מ‑WLED ו‑self‑declaring מ‑Pixelblaze). כך מושגת שליטה מלאה בלי חשיפת single‑pixels.

### 2.2 שני טיפוסי אפקט

| טיפוס | יעד | מודל |
|---|---|---|
| **PixelEffect** | staff, progressbar | מרחבי — פאטרן על N פיקסלים |
| **ChannelEffect** | dmx | ערוצי — dimmer/צבע/strobe over time |

**משותף:** UI, ספריית אפקטים, סכמת בּיינדינג לטלמטריה.
**נפרד:** מנוע רינדור + בקר יעד.

### 2.3 קדימה‑תאימות לשלב 2 (עיקרון מנחה)

כל פרמטר בסכמה הוא **או קבוע או binding**. בשלב 1 כל ה‑bindings הם `null`. הסכמה כבר מכילה את המבנה כדי שקשירת טלמטריה בשלב 2 לא תדרוש שכתוב.

```js
param = { value: <const>, binding: null }              // שלב 1
param = { value: <fallback>, binding: {                // שלב 2
  source: "gz" | "speed" | "rollSpeed" | "ax" | ...,
  transfer: { in: [min,max], out: [min,max], curve: "linear"|"ease" }
}}
```

---

## 3. סיכום ההחלטות שנסגרו

| נושא | החלטה |
|---|---|
| **מודל רינדור** | מנוע **פרמטרי מהיסוד** (חובה לשלב 2). מצב baked/POV מתווסף מאוחר יותר כשכבה. |
| **ניתוב** | שידור ESP‑NOW פרמטרי אחיד עם `targetRole`; כל בקר מסנן לשלו. |
| **Staff v1** | Pattern 1D על 25 פיקסלים. **segment‑ready** אך ברירת מחדל = segment יחיד. POV = טיפוס עתידי. |
| **ליבת אפקטים v1** | Solid, Gradient, Wave, Fade, Sparkle. |
| **DMX** | קבוצת fixtures ממוענת, מצבי Unison/Spatial, פרופיל WWRGB + strobe + fade. |
| **צבע DMX** | RGB + **WW כערוץ עצמאי** (סליידר נפרד, ללא חישוב אוטומטי). |
| **Zero‑Touch** | מודולים חדשים עצמאיים, אפס נגיעה בקוד הנעול. |

**Open Questions (לסוכן, לא חוסמות אפיון):**
- **A** — מבנה ה‑struct של ESP‑NOW: האם המערכת כבר **מודל 1** (שדות פרמטרים) או **מודל 3** (אינדקס לאפקט מקודד‑קשיח). אם מודל 3 → נדרש שלב המרת פירמוור למנוע פרמטרי לפני אינטגרציה.
- **B** — segments על הסטאף: משטח רציף יחיד מול אזורים בלתי‑תלויים. תלוי בתמיכת הפירמוור.

---

## 4. סכמת EffectDefinition

מבנה נתונים אחיד שנשמר בספרייה (IndexedDB, כמו נתוני האימון). זהו הפלט של ה‑Composer והקלט של הרינדור.

```js
EffectDefinition {
  id:        string,          // uuid
  name:      string,          // שם בעברית, מוצג בספרייה
  version:   1,
  type:      "pixel" | "channel",
  targetRole:"staff" | "progressbar" | "dmx",

  algorithm: string,          // ראה §5 (pixel) / §6 (channel)

  colors: {
    primary:   {value:"#RRGGBB", binding:null},
    secondary: {value:"#RRGGBB", binding:null},
    tertiary:  {value:"#RRGGBB", binding:null},
    ww:        {value:0..255,    binding:null}   // channel בלבד
  },
  palette:  { value: <paletteId|null>, binding:null },

  params: {                   // רק הפרמטרים שהאלגוריתם מכריז עליהם
    <name>: {value:<const>, binding:null}
  },

  segment: {                  // pixel בלבד; segment-ready
    mode: "single",           // v1 default; "multi" תלוי ב-Open Question B
    ranges: [[0, LEN-1]]
  },

  fixtures: [                 // channel בלבד
    { address:int, profile:"WWRGB_SF" }
  ],
  spatialMode: "unison" | "spatial"   // channel בלבד
}
```

> 💡 המנוע הפרמטרי מקבל את המבנה הזה ומרנדר. הבקר **אינו** מקבל pixel buffer — הוא מקבל את הפרמטרים ומרנדר מקומית (זול ב‑ESP‑NOW, ומאפשר שלב 2).

---

## 5. ליבת אפקטי Pixel — v1

חמישה אלגוריתמים. כל אחד מכריז אילו בקרות הוא משתמש (ה‑UI מסתיר את השאר).

| אלגוריתם | תיאור | פרמטרים מוכרזים | צבעים | פרימיטיב FastLED |
|---|---|---|---|---|
| **solid** | צבע אחיד | brightness | primary | `fill_solid` |
| **gradient** | מעבר צבעים לאורך הרצועה | direction, blend | primary, secondary (או palette) | `fill_gradient` / `ColorFromPalette` |
| **wave** | אוסילטור נע לאורך הרצועה | speed(bpm), width, direction | primary (או palette) | `beatsin8` + מיפוי מרחבי |
| **fade** | אוסילטור בהירות גלובלי (breathe/pulse) | speed(bpm), minBri, maxBri | primary (או palette) | `beatsin8` על brightness גלובלי |
| **sparkle** | הבזקים אקראיים עם זנב | density, decay(fade‑tail), speed | primary(base), secondary(spark) | `random8` + `fadeToBlackBy` |

**הערות מנוע:**
- `wave` ו‑`fade` חולקים את אותו אוסילטור (`beatsin8`) — ההבדל הוא מה מווסת: `wave` מזיז צבע במרחב, `fade` מווסת בהירות אחידה. ב‑UI הם שני אפקטים נפרדים כי החוויה שונה.
- `intensity` האוניברסלי ממופה למשמעות פר‑אפקט (למשל `density` ב‑sparkle, `width` ב‑wave) — בדיוק כמו במוסכמת WLED.

---

## 6. ChannelEffect — DMX

### 6.1 מודל היעד

בקר DMX נפרד מקבל את אותה הודעת ESP‑NOW פרמטרית (מסוננת לפי `targetRole:"dmx"`) ומתרגם מקומית ל‑DMX. **האפקט מותאם לטיפוס הכלי — לא נשטח מ‑pixel.**

### 6.2 fixtures וכתובות

השרשרת: 2 פנסים על כבל DMX אחד, בקר אחד מזין. כל פנס בכתובת DMX משלו → עצמאות. מתרחב ל‑N פנסים באותו מודל.

```js
fixtures: [
  { address:1, profile:"WWRGB_SF" },
  { address:9, profile:"WWRGB_SF" }
]
```

### 6.3 פרופיל ערוצים — WWRGB_SF

| ערוץ | תפקיד | הערה |
|---|---|---|
| WW | לובן חם | **ציר עצמאי** — סליידר נפרד, ללא חישוב מ‑RGB |
| R / G / B | צבע | מקור הצבע העיקרי |
| Strobe | הבהוב | **ערוץ חומרה ייעודי** — לא מסומלץ מ‑dimmer |
| Fade | החלקת מעברים בחומרה | **ברירת מחדל 0** — כל ההחלקה מהמנוע, למניעת double‑fade |

### 6.4 מצבי הפעלה

| מצב | התנהגות |
|---|---|
| **Unison** | אותו אפקט על כל הפנסים בו‑זמנית |
| **Spatial** | הפאטרן מתפרש על פני הפנסים לפי סדר הכתובות (chase / mirror / A→B) — "surface" של N fixtures |

---

## 7. ניתוב ESP‑NOW

- כל הודעה נושאת `targetRole` (staff / progressbar / dmx).
- כל בקר מסנן: הסטאף מתעלם מהודעות dmx ולהפך.
- מתאים ל‑broadcast: הודעה אחת ברשת, כל מקבל מגיב רק לשלו ומרנדר עם המנוע המתאים לו.

```
ESP-NOW (parametric, targetRole)
        │  broadcast
        ├──► Staff controller     → PixelEngine  (25px)
        ├──► Progressbar ctrl     → PixelEngine  (strip)
        └──► DMX controller       → ChannelEngine → DMX chain
```

---

## 8. אינטגרציית Zero‑Touch — דפוס מוצע

הדפוס נגזר מהמודולים של הפרויקט המקורי (Smart Staff): מודול חדש עצמאי, wrap‑hook, IndexedDB, אפס נגיעה בליבת הרינדור/הפריסטים. שמות הקבצים למטה **אילוסטרטיביים** — הסוכן ממפה אותם למקבילות בפועל בפרויקט החדש.

| קובץ (אילוסטרטיבי) | סטטוס | תוכן |
|---|---|---|
| `effect_composer.js` | חדש ➕ | לוגיקת עריכה, סכמת EffectDefinition, ספרייה, export/import |
| `effect_renderer.js` | חדש ➕ | מנוע preview על `<canvas>` — מרנדר את EffectDefinition לתצוגה מקדימה |
| נקודת ניווט + עמוד ייעודי | שינוי ✏️ | הרחבה בלבד של מנגנון הניווט הקיים, בדפוס של הוספת עמוד |
| מנוע האפקטים הקיים | נעול ✅ | אין שינוי (מקביל ל‑`effects_engine.js` המקורי) |
| מקור הפריסטים הקיים | נעול ✅ | אין שינוי — פריסטים ישנים ניתנים לייבוא לספרייה החדשה |

> 💡 ה‑preview בדאשבורד הוא סימולציה. ה‑ground truth הוא הרינדור בבקר. יש לוודא שהמנוע בדאשבורד והמנוע בפירמוור מיישמים את אותם פרמטרים באותו אופן (ראה §10, בדיקת render‑parity).

---

## 9. בריף UI — Effect Composer

דף חדש בארכיטקטורת `showPage()` הקיימת. ערכת עיצוב זהה: dark theme, `.card`, RTL, משתני CSS קיימים.

**מבנה המסך (טור אחד, scroll רציף):**

1. **Target Selector** — staff / progressbar / dmx. קובע איזה טיפוס אפקט וזמין (Pixel/Channel) ואילו בקרות מוצגות.
2. **Algorithm Picker** — בחירת אלגוריתם מ‑§5/§6. בבחירה, ה‑UI מרנדר רק את הבקרות שהאלגוריתם מכריז עליהן.
3. **Color Panel** — primary/secondary/tertiary + palette. ל‑DMX נוסף סליידר WW עצמאי.
4. **Parameter Panel** — סליידרים דינמיים לפי הצהרת האלגוריתם (speed, intensity, ועוד).
5. **Live Preview** — `<canvas>` שמרנדר את האפקט בזמן אמת בזמן כוונון.
6. **Library** — שמירה בשם, טעינה, שכפול, מחיקה, Export/Import JSON.

**הנחיות עיצוב:**
- הסתרת בקרות לא‑רלוונטיות (WLED‑style) — לא להשאיר סליידר מת.
- ל‑DMX Spatial: תצוגת סדר ה‑fixtures (A→B) לצד ה‑preview.
- palette dropdown = searchable (הרבה פלטות — לא רשימה סטטית).

---

## 10. חבילת בדיקות

בדיקות קבלה. נכשלה בדיקה חוסמת → אין merge עד תיקון.

### 10.1 Zero‑Touch (חוסם)
1. לאחר הוספת המודולים — דף **Live Show** עובד זהה לחלוטין: סימולטור, faders, hotkeys, פריסטים קיימים.
2. `effects_engine.js` ו‑`presets.js` — diff ריק. אין שינוי בייט.

### 10.2 סכמה וקדימה‑תאימות (חוסם)
3. EffectDefinition עם `binding:null` בכל הפרמטרים מרנדר תקין (נתיב שלב 1).
4. EffectDefinition עם binding stub (mock) **אינו שובר** את v1 — ה‑fallback ל‑`value` פועל.
5. Export → Import round‑trip משמר את המבנה בדיוק.

### 10.3 רינדור Pixel
6. כל אחד מ‑5 האלגוריתמים מרנדר ב‑preview ללא שגיאה.
7. שינוי פרמטר בודד (למשל `speed`) משתקף **ברציפות** ב‑preview — לא רק בהחלפת אפקט. *(זו גם בדיקת ה‑discriminator של מודל 1 מול מודל 3 — ראה Open Question A.)*
8. render‑parity: אותו EffectDefinition נותן תוצאה עקבית בין preview לבין רינדור הבקר (בטווח הסביר של הבדלי חומרה).

### 10.4 DMX / ChannelEffect
9. ChannelEffect מתורגם לערכי DMX נכונים **פר‑כתובת** — פנס בכתובת 1 ופנס בכתובת 9 עצמאיים.
10. Strobe מפעיל את **ערוץ החומרה**, לא הבהוב dimmer.
11. ערוץ Fade בחומרה = 0 כברירת מחדל (אין double‑fade).
12. Spatial mode: chase נע A→B לפי סדר הכתובות; Unison: שניהם בסנכרון.

### 10.5 ניתוב
13. הודעת `targetRole:"dmx"` אינה משפיעה על הסטאף; הודעת `targetRole:"staff"` אינה משפיעה על ה‑DMX.

---

## 11. מה לא בסקופ

| נושא | הערה |
|---|---|
| קשירת טלמטריה לפרמטרים | שלב 2. הסכמה כבר מוכנה (bindings). |
| POV / baked image mode | טיפוס עתידי, מתווסף כשכבה על המנוע הפרמטרי. |
| segments מרובים על הסטאף | תלוי ב‑Open Question B. הסכמה segment‑ready. |
| מנוע אפקטים בפירמוור | אם Open Question A = מודל 3, זהו תת‑פרויקט המרה נפרד. |

---

*Smart Staff Dashboard | Antigravity Project | v0.1 | הצעת שדרוג לשיקול הסוכן — לא תוכנית ביצוע מחייבת.*

"""The effects people can add to a video, in Persian, with the options each one understands.

All 42 effects of the vendored core (``_fx``). Text is drawn with Vazirmatn whenever it contains Persian (engine/face_effects/_fa.py joins the letters);
effects whose built-in labels are English decor (a Follow button, REC, a timeline) keep them. ``use`` tells the director when an effect fits.
"""
from __future__ import annotations

import re

MAX_EFFECTS = 12
MIN_SECONDS, MAX_SECONDS = 0.4, 8.0
GRADES = ("moody", "bw", "warm", "cool", "pop")


def _num(key, label, low, high, default, step=0.05):
    return {"key": key, "label": label, "type": "number", "min": low, "max": high, "default": default, "step": step}


CATALOG: list[dict] = [
    {"id": "orbit", "title": "چرخش دور سر", "description": "قاب‌های ویدیو مثل مدار دور سرت می‌چرخند؛ پایین جلوی تو و بالا پشت سرت.",
     "options": [_num("count", "تعداد قاب", 3, 10, 6, 1), _num("speed", "سرعت چرخش", 0.5, 4, 1.9)]},
    {"id": "noise", "title": "ریل‌های پشت سر", "description": "قاب‌های ریل یکی‌یکی پشت سرت جمع می‌شوند.", "options": [_num("size", "اندازه قاب‌ها", 0.2, 0.5, 0.34)]},
    {"id": "locked-on", "title": "قفل روی صورت", "description": "چهار گوشه روی صورتت قفل می‌شود و دوربین دنبالت می‌آید.",
     "text": {"label": "برچسب زیر قاب (اختیاری)", "default": ""}, "options": [_num("zoom", "بزرگ‌نمایی", 1.0, 1.8, 1.35)]},
    {"id": "lean-in", "title": "پانچ‌این سریع", "description": "یک نزدیک‌شدن سریع روی صورت، مناسب یک کلمهٔ مهم.",
     "options": [_num("zoom", "بزرگ‌نمایی", 1.1, 2.0, 1.45), _num("speed", "مدت ورود (ثانیه)", 0.08, 0.6, 0.18)]},
    {"id": "spotlight", "title": "نورافکن", "description": "نور محیط خاموش می‌شود و فقط تو روشن می‌مانی؛ می‌توانی یک کلمهٔ درخشان پشت سرت بگذاری.",
     "text": {"label": "کلمهٔ درخشان پشت سر (اختیاری)", "default": ""}, "options": [_num("push", "نزدیک‌شدن", 1.0, 1.4, 1.1), {"key": "color", "label": "رنگ کلمه", "type": "color", "default": "#FFB7A5"}]},
    {"id": "moody", "title": "گرید رنگی", "description": "یک حال‌وهوای رنگی روی تصویر.", "options": [{"key": "grade", "label": "حالت", "type": "choice", "choices": list(GRADES), "default": "moody"}]},
    {"id": "swipe", "title": "قبل و بعد", "description": "یک لغزندهٔ قبل/بعد روی تصویر می‌کشد.",
     "options": [{"key": "grade", "label": "ظاهر «بعد»", "type": "choice", "choices": list(GRADES), "default": "moody"}]},
    {"id": "rabbit-hole", "title": "تونل", "description": "اتاق پشت سرت مثل تونل می‌چرخد و عمیق می‌شود.",
     "options": [_num("ratio", "عمق", 0.4, 0.8, 0.62), _num("speed", "سرعت", 0.3, 2, 0.8), _num("spin", "چرخش", 0, 25, 10, 1)]},
    {"id": "dot-reveal", "title": "ظاهر شدن با نقطه‌ها", "description": "تصویر از نقطه‌های درخشان ساخته می‌شود و بعد واضح می‌شود.",
     "options": [{"key": "color", "label": "رنگ نقطه‌ها", "type": "color", "default": "#FF8050"}, _num("cell", "اندازه نقطه‌ها", 0.01, 0.04, 0.017, 0.001)]},
    {"id": "slow-push", "title": "پوش آرام سینمایی", "description": "آهسته به صورتت نزدیک می‌شود و اتاق کم‌کم محو می‌شود.",
     "options": [_num("zoom", "بزرگ‌نمایی", 1.1, 2.0, 1.6), _num("blur", "محوشدگی اتاق", 0, 0.02, 0.006, 0.001)]},
]


def _text(label, default="", lines=None):
    spec = {"label": label, "default": default}
    if lines:
        spec["lines"] = lines
    return spec


def _color(label="رنگ", default="#FF4D4D"):
    return {"key": "color", "label": label, "type": "color", "default": default}


def _fx(id, title, description, use, text=None, options=None):
    item = {"id": id, "title": title, "description": description, "use": use, "options": options or []}
    if text:
        item["text"] = text
    return item


CATALOG += [
    _fx("lineup", "ردیف شماره‌دار", "کاشی‌های شماره‌دار مثل بادبزن بالای سرت باز می‌شوند.", "فهرست چندمرحله‌ای یا چند نکته‌ی پشت‌سرهم",
        _text("عنوان کاشی‌ها با | جدا شوند", "اول|دوم|سوم|چهارم", 6)),
    _fx("backdrop-word", "کلمه‌ی غول‌پیکر پشت سر", "یک کلمه‌ی بزرگ پشت سرت می‌افتد و تو جلوی آن می‌مانی.", "یک کلمه‌ی کلیدی یا عنوان بحث",
        _text("کلمه (کوتاه)", "فروش", 1), [_color("رنگ کلمه", "#FFFFFF")]),
    _fx("the-bill", "فاکتور چاپی", "هر مورد مثل یک فاکتور روی دیوار بالای سرت چاپ می‌شود.", "مرور سفارش، مراحل یا هزینه‌ها",
        _text("خط‌های فاکتور با | جدا شوند", "سفارش ۱۰۲۱|یک مورد|دو مورد|تمام", 8)),
    _fx("todo", "چک‌لیست کنار سر", "کارت چک‌لیست کنار سر که با حرف زدنت تیک می‌خورد.", "مراحل یک روش یا کارهای لازم",
        _text("موارد با | جدا شوند", "اول مرحله‌ی اول|بعد مرحله‌ی دوم|آخر تمام", 5)),
    _fx("tap", "دکمه‌ی دنبال‌کردن", "دکمه‌ی Follow ظاهر می‌شود و به Following تبدیل می‌شود.", "دعوت به دنبال‌کردن، معمولاً آخر ویدیو"),
    _fx("pause-point", "ایست و اشاره", "تصویر می‌ایستد و یک فلش دست‌کشیده به نقطه‌ای اشاره می‌کند.", "جلب توجه به یک جزئیات",
        _text("برچسب کنار فلش", "اینجا ببین", 1), [_color("رنگ فلش", "#FFD60A")]),
    _fx("uninstall", "نوار حذف گلیچی", "یک نوار پیشرفت گلیچی و بعد خرد‌شدن تصویر.", "حذف یک عادت یا باور غلط",
        _text("متن نوار", "در حال حذف...", 1)),
    _fx("reel-frame", "قاب ریلز", "ویدیو در قاب یک ریلز اینستاگرام کوچک می‌شود.", "حس شبکه‌ی اجتماعی؛ معرفی یا جمع‌بندی",
        _text("هندل", "@نمونه", 1)),
    _fx("shortcut-rain", "بارش کلیدها", "کلیدهای کیبورد پشت سرت می‌بارند.", "ابزار، نرم‌افزار و میان‌بر",
        _text("کلیدها با | جدا شوند", "cmd|/|C|V|Z|esc|tab", 1), [_num("count", "تعداد", 10, 40, 26, 1)]),
    _fx("reject-stamp", "مهر «رد شد»", "یک مهر بزرگ قرمز روی تصویر می‌خورد.", "رد یک باور یا اشتباه رایج",
        _text("متن مهر", "رد شد", 1), [_color("رنگ مهر", "#E02020")]),
    _fx("countdown-flip", "شمارش معکوس", "ساعت ورق‌خورِ ۳، ۲، ۱ بالای سرت.", "شروع یک بخش مهم یا هیجان",
        None, [_num("from", "شروع از", 2, 9, 3, 1)]),
    _fx("cover-star", "کاور مجله", "تو کاور مجله می‌شوی و عنوان پشت سرت است.", "معرفی یک موضوع بزرگ یا دستاورد",
        _text("کلمه‌ی عنوان", "ایده", 1)),
    _fx("scribble", "خط‌خطی مارکر", "دودل‌های مارکری دور سرت کشیده می‌شوند.", "حس خودمانی و خلاق",
        _text("کلمه‌ی خطی", "من!", 1), [_color("رنگ", "#FFD60A")]),
    _fx("red-collage", "کلاژ قرمز", "تصویر سیاه‌وسفید با کلمه‌ی قرمز بزرگ و تایپ متحرک.", "ادعای قوی و پرانرژی",
        _text("کلمه‌ی قرمز", "ادیت", 1), [_color("رنگ", "#E02020")]),
    _fx("split-headline", "تیتر از بالا", "یک کارت تیتر از بالا می‌لغزد و تو را پایین قاب می‌گذارد.", "گفتن موضوع یا وعده‌ی ویدیو",
        _text("تیتر با | در چند خط", "محصول دیجیتال|بدون مرز|بفروش", 3), [_color("رنگ کلمه‌ی ویژه", "#FFD60A")]),
    _fx("pastel-word", "کلمه‌ی پاستلی", "پس‌زمینه‌ی ملایم بنفش، کلمه‌ی بزرگ پشت سر و کارت پروفایل.", "معرفی خودت یا موضوع به‌صورت نرم",
        _text("کلمه", "ریلز", 1)),
    _fx("check-pills", "قرص‌های تیک‌دار", "اتاق شبیه کاغذ شطرنجی می‌شود و قرص‌های آبی یکی‌یکی تیک می‌خورند.", "فهرست کوتاه موارد قابل‌انتخاب",
        _text("موارد با | جدا شوند", "هوک|زیرنویس|برش", 4)),
    _fx("headline-box", "پانچ‌این با تیتر", "نزدیک‌شدن سریع با یک تیتر دوخطی و خط دوم داخل جعبه‌ی سفید.", "عنوان بحث در لحظه‌ی شروع",
        _text("دو خط با | جدا شوند", "چطور محصول دیجیتال|بفروشیم", 2), [_num("zoom", "بزرگ‌نمایی", 1.0, 1.6, 1.2)]),
    _fx("profile-wall", "دیوار پروفایل و شمارنده", "شبکه‌ی ویدیوهایت پشت سر پر می‌شود و شمارنده بالا می‌رود.", "اثبات اجتماعی و عدد بازدید",
        None, [_num("count", "عدد نهایی", 1000, 9000000, 197000, 1000)]),
    _fx("tier-list", "تیرلیست", "یک جدول رتبه جلوی تو می‌افتد و یک مورد به بهترین ردیف می‌رود.", "مقایسه و انتخاب بهترین گزینه",
        _text("نام گزینه‌ی برنده", "ما", 1)),
    _fx("broll-split", "اسپلیت با برچسب قیمت", "صفحه دو نیم می‌شود؛ بالا تصویر دیگر با برچسب، پایین تو.", "قبل/بعد، عدد، صرفه‌جویی زمان یا هزینه",
        _text("متن برچسب", "۴ ساعت ← ۴ دقیقه", 1)),
    _fx("phone-fan", "بادبزن گوشی‌ها", "ریلزهایت مثل چند گوشی بادبزنی جلوی تو باز می‌شوند.", "نمونه‌کار یا چندین مثال",
        _text("تیتر دوخطی با |", "محصول دیجیتال|بدون مرز", 2)),
    _fx("headline-wall", "دیوار تیترها", "تیترهای ویدیوهایت پشت سر جمع می‌شوند و مجموع بازدید جلو می‌آید.", "اعتبار و سابقه",
        _text("تیترها با | و بازدیدها با ::", "", 8)),
    _fx("checklist", "لیست کار زنده", "یک لیست کار زیر چانه ساخته می‌شود و هر مرحله چرخیده تیک می‌خورد.", "فرآیند چندمرحله‌ای که انجام می‌شود",
        _text("مراحل با | و توضیح با ::", "چهره پیدا شد::هر فریم|برش خورد::تمیز", 5)),
    _fx("glass-widgets", "ویجت‌های شیشه‌ای", "ویجت‌های شیشه‌ای موبایل دور سرت شناور می‌شوند.", "حس مدرن و اپلیکیشنی"),
    _fx("timeline", "تایم‌لاین ادیت", "گرید قرمز سینمایی با تایم‌لاین، REC و پلی‌هد درخشان.", "نشان‌دادن پشت‌صحنه‌ی ادیت",
        _text("کلمه‌ی بالا", "ادیت", 1)),
    _fx("comment-box", "باکس کامنت", "صفحه‌ی کامنت اینستاگرام بالای سرت کلمه را تایپ و ارسال می‌کند.", "دعوت به کامنت‌گذاشتن"),
    _fx("liquid-glass-graph", "نمودار شیشه‌ای", "کارت شیشه‌ای زیر چانه، نمودار بالا می‌رود و عدد شمرده می‌شود.", "رشد، درصد یا نتیجه‌ی عددی",
        _text("برچسب نمودار", "بازدید", 1), [_color("رنگ نمودار", "#30D158")]),
    _fx("carousel-spin", "چرخ‌فلک تصاویر", "فریم‌های ویدیو دور تو مثل چرخ‌فلک سه‌بعدی می‌چرخند و می‌ایستند.", "تنوع، مجموعه یا نمونه‌های زیاد",
        None, [_num("turns", "تعداد دور", 0.5, 3, 1.1), _num("size", "اندازه", 0.2, 0.45, 0.3)]),
    _fx("match-cut", "برش خبری", "صفحه‌های خبر روی یک کلمه برش می‌خورند و پشت سر قفل می‌شوند.", "اشاره به خبر یا رویداد"),
    _fx("apple-toggles", "سوییچ‌های آیفون", "کارت تنظیمات آیفون زیر چانه، سوییچ‌ها یکی‌یکی روشن می‌شوند.", "مزیت‌ها یا ویژگی‌های روشن‌شده",
        _text("موارد با | جدا شوند", "یک ویدیو|بدون اپ|بدون ادیتور", 4)),
    _fx("led-sign", "تابلوی LED", "نورها خاموش می‌شوند و یک تابلوی LED کلمه را پشت سرت تایپ می‌کند.", "شعار یا کلمه‌ی پایانی",
        _text("متن تابلو", "فروش", 1), [_color("رنگ نور", "#FF9230")]),
]

USE = {"orbit": "نمایش چند نمونه یا ویدیو دور گوینده", "noise": "پر شدن تدریجی نمونه‌ها یا ریل‌ها", "locked-on": "تمرکز روی گوینده در لحظه‌ی مهم",
       "lean-in": "تأکید روی یک کلمه‌ی کلیدی", "spotlight": "لحظه‌ی جدی یا افشاگری", "moody": "حال‌وهوای تیره و سینمایی", "swipe": "قبل و بعد",
       "rabbit-hole": "ورود به یک موضوع عمیق", "dot-reveal": "شروع یا معرفی با حس تکنولوژی", "slow-push": "لحظه‌ی احساسی یا نتیجه‌گیری"}
for _item in CATALOG:
    _item.setdefault("use", USE.get(_item["id"], ""))

BY_ID = {item["id"]: item for item in CATALOG}
_COLOR = re.compile(r"#[0-9a-fA-F]{6}")


class EffectsError(ValueError):
    pass


def clean_plan(raw, *, duration: float | None = None) -> list[dict]:
    """Shape-check a list of effects: known ids, a sensible window, only the options each effect has, values inside their limits."""
    if raw in (None, []):
        return []
    if not isinstance(raw, list):
        raise EffectsError("فهرست افکت‌ها معتبر نیست.")
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise EffectsError("افکت معتبر نیست.")
        fx = str(item.get("fx") or "").strip().lower()
        spec = BY_ID.get(fx)
        if spec is None:
            raise EffectsError(f"این افکت وجود ندارد: {fx[:30]}")
        try:
            start, end = float(item.get("start")), float(item.get("end"))
        except (TypeError, ValueError):
            raise EffectsError("زمان شروع و پایان افکت باید عدد باشد.")
        if not (0 <= start < end <= 36000):
            raise EffectsError("زمان افکت معتبر نیست.")
        if duration:
            end = min(end, float(duration))
            if end - start < 0.2:
                raise EffectsError("افکت بیرون از طول ویدیو است.")
        if not MIN_SECONDS <= end - start <= MAX_SECONDS:
            raise EffectsError(f"مدت هر افکت باید بین {MIN_SECONDS:g} و {MAX_SECONDS:g} ثانیه باشد.")
        clean: dict = {"fx": fx, "start": round(start, 2), "end": round(end, 2)}
        if "text" in spec:
            text = " ".join(str(item.get("text") or "").split())[:160]
            if text:
                clean["text"] = text
        for option in spec.get("options", []):
            key = option["key"]
            if key not in item or item[key] in (None, ""):
                continue
            value = item[key]
            if option["type"] == "number":
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    raise EffectsError(f"مقدار «{option['label']}» باید عدد باشد.")
                clean[key] = round(max(option["min"], min(option["max"], number)), 4)
            elif option["type"] == "choice":
                if value not in option["choices"]:
                    raise EffectsError(f"مقدار «{option['label']}» معتبر نیست.")
                clean[key] = value
            elif option["type"] == "color":
                if not _COLOR.fullmatch(str(value)):
                    raise EffectsError(f"رنگ «{option['label']}» معتبر نیست.")
                clean[key] = str(value).upper()
        out.append(clean)
    if len(out) > MAX_EFFECTS:
        raise EffectsError(f"حداکثر {MAX_EFFECTS} افکت ممکن است.")
    return out

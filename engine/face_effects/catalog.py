"""The effects people can add to a video, in Persian, with the options each one understands.

Phase 1: the effects that need no text of their own. The vendored core (``_fx``) holds 42; the rest are enabled once their text is localised.
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
            text = " ".join(str(item.get("text") or "").split())[:40]
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

"""Creative Plan: what the studio intends to produce, in plain language, versioned, approved by the user.

AI proposes, the user approves, then production starts. The plan is built from the real analysis
(transcript, creative direction and the engine's own decisions) and from the user's brand profile;
nothing in it is a capability the engine cannot execute. Every edit that changes the output creates a
new version and clears approval; render may start only through ``approve(state, version_id)`` with the
current version's id.

The plan lives in the Studio project state under ``plan``::

    {"versions": [{"id", "n", "source", "note", "created_at", "fingerprint", "content"}],
     "approved_id": str | None}

and the workflow position under ``workflow`` (see ``WORKFLOW``).
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
import uuid

WORKFLOW = ("input_received", "analyzing", "awaiting_approval", "approved", "production",
            "quality_evaluation", "user_review", "completed", "failed")

STYLES = {
    "talking_1": {
        "label": "کلاسیک صحبتی", "summary": "تمام‌قاب روی گوینده با جامپ‌کات، هوک ثابت بالای تصویر و چند لحظهٔ سیاه‌وسفید برای جمله‌های مهم.",
        "captions": "کپشن پررنگ سفید وسط پایین تصویر", "motion": "زوم نرم بین نمای باز و بسته روی صورت",
        "broll": "بدون تصویر مکمل؛ تمرکز کامل روی گوینده", "sfx": "موسیقی ملایم زیر صدا", "complexity": "ساده",
        "pictures": False,
    },
    "talking_2": {
        "label": "آموزشی دوتکه", "summary": "نیمهٔ بالا تصویر یا گرافیکِ هر جمله، نیمهٔ پایین گوینده؛ فهرست‌ها به‌صورت چیپ ظاهر می‌شوند.",
        "captions": "یک تا دو کلمه روی خط وسط: کلمهٔ کوچک سفید و کلیدواژهٔ بزرگ رنگی", "motion": "کارت تصویر با زوم آرام و چیپ‌های متحرک",
        "broll": "برای هر بخش یک تصویر: فایل‌های شما، کتابخانه یا تصویر ساخته‌شده با هوش مصنوعی", "sfx": "موسیقی پرانرژی‌تر، صدای بلندتر (-14 LUFS)",
        "complexity": "متوسط", "pictures": True,
    },
    "talking_3": {
        "label": "سینمایی", "summary": "تصویر سینمایی تمام‌عرض بالا و گوینده پایین، عنوان‌های فصل‌بندی‌شده و رنگ‌بندی تیل‌ونارنجی.",
        "captions": "یک تا سه کلمهٔ سفید مینیمال روی خط وسط", "motion": "حرکت آرام دوربین روی تصویر، کارت‌های کج و درخشان، عنوان‌های ادیتوریال",
        "broll": "تصویرهای سینمایی برای هر بخش (فایل‌های شما، کتابخانه یا هوش مصنوعی)", "sfx": "موسیقی سینمایی با پالس، گرین فیلم و وینیت",
        "complexity": "پیشرفته", "pictures": True,
    },
    "talking_4": {
        "label": "مینیمال واقعی", "summary": "تصویر طبیعی گوینده بدون افکت سنگین، هوک طلایی بزرگ در ثانیه‌های اول و کپشن خوانا.",
        "captions": "کپشن چندکلمه‌ای سفید با کلیدواژهٔ رنگی", "motion": "تایپوگرافی متحرک برای هوک و لحظه‌های کلیدی",
        "broll": "بدون تصویر مکمل", "sfx": "موسیقی ملایم زیر صدا", "complexity": "ساده", "pictures": False,
    },
}

LOOKS = {
    # The Talking engine's own default grade (app/talking_reel.DEFAULTS); each style adds its own treatment.
    "default": {"label": "پیش‌فرض سبک", "grade": {"brightness": 0, "contrast": 100, "saturation": 100, "temperature": 0, "vignette": 50}},
    "natural": {"label": "طبیعی", "grade": {"brightness": 0, "contrast": 100, "saturation": 100, "temperature": 0, "vignette": 0}},
    "warm": {"label": "گرم", "grade": {"brightness": 0, "contrast": 108, "saturation": 100, "temperature": 12, "vignette": 20}},
    "cool": {"label": "سرد و ملایم", "grade": {"brightness": 0, "contrast": 104, "saturation": 92, "temperature": -10, "vignette": 15}},
    "cinematic": {"label": "سینمایی", "grade": {"brightness": -4, "contrast": 116, "saturation": 84, "temperature": 8, "vignette": 45}},
}
FONTS = {"default": "فونت اصلی سبک (Ray)", "Vazirmatn": "وزیرمتن"}


class PlanError(ValueError):
    pass


def look_of(grade: dict) -> str:
    """The named look whose grade matches, else "custom" (the user tuned values by hand)."""
    for key, look in LOOKS.items():
        if all(int(grade.get(k, v)) == v for k, v in look["grade"].items()):
            return key
    return "custom"


def _hook(status: dict) -> str:
    return str((status.get("hook") if status.get("style") == "talking_1" else status.get("hook2")) or status.get("hook") or "")


def _time(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    return f"{seconds // 60}:{seconds % 60:02d}"


def build_talking(status: dict, *, sentences: list[dict], video_seconds: float, estimate: dict | None,
                  has_logo: bool) -> dict:
    """Plain-language plan from the Talking engine's public state after analysis."""
    style = str(status.get("style") or "talking_1")
    info = STYLES.get(style, STYLES["talking_1"])
    creative = status.get("creative_plan") or {}
    brief = creative.get("brief") or {}
    chosen = creative.get("chosen") or {}
    settings = status.get("render_settings") or {}
    grade = settings.get("grade") or {}
    beats = []
    for beat in chosen.get("beats") or []:
        index = beat.get("sentence")
        line = sentences[index] if isinstance(index, int) and 0 <= index < len(sentences) else None
        beats.append({"role": beat.get("role", ""), "intent": beat.get("intent", ""), "visual": beat.get("visual", ""),
                      "sentence": index, "at": _time(line["start"]) if line else "", "text": line["text"] if line else ""})
    pictures = [{"sentence": item.get("i"), "title": item.get("title", ""), "visual_type": item.get("visual_type", "")}
                for item in status.get("storyboard") or []] if info["pictures"] else []
    concepts = []
    if chosen:
        concepts.append({"id": chosen.get("id") or "chosen", "name": chosen.get("name", ""), "angle": chosen.get("angle", ""),
                         "hook": chosen.get("hook", ""), "style": style, "selected": True,
                         "why": creative.get("verdict", "")})
    for alt in creative.get("alternatives") or []:
        alt_style = alt.get("style_hint") if alt.get("style_hint") in STYLES else style
        concepts.append({"id": alt.get("id"), "name": alt.get("name", ""), "angle": alt.get("angle", ""),
                         "hook": alt.get("hook", ""), "style": alt_style, "selected": False,
                         "why": alt.get("why_it_works", "")})
    logo = settings.get("outro_logo") or {}
    return {
        "kind": "talking",
        "goal": brief.get("goal") or "ریلز حرفه‌ای اینستاگرام از ویدیوی صحبتی",
        "audience": brief.get("audience", ""),
        "message": brief.get("core_message") or brief.get("topic", ""),
        "tone": brief.get("tone", ""),
        "concept": {"name": chosen.get("name", ""), "angle": chosen.get("angle", "")},
        "hook": {"text": _hook(status), "highlight": list(status.get("hook_highlight") or [])},
        "structure": beats,
        "duration_s": round(video_seconds, 1),
        "style": {"id": style, "label": info["label"], "summary": info["summary"], "complexity": info["complexity"]},
        "look": {"preset": look_of(grade), "grade": grade, "accent_color": settings.get("title_color") or "#F5B800",
                 "caption_font": settings.get("caption_font") or "default",
                 "zoom": (settings.get("zoom") or {}).get("amount", 100),
                 "key_moments": bool(settings.get("key_moments_enabled", True))},
        "captions": info["captions"], "motion": info["motion"], "broll": info["broll"], "pictures": pictures,
        "audio": {"music": (status.get("music") or "").rsplit("/", 1)[-1], "voice": "صدای اصلی گوینده (بدون نریشن جدید)",
                  "sfx": info["sfx"]},
        "brand": {"name": status.get("name", ""), "tagline": status.get("title", ""), "cta": status.get("cta", ""),
                  "logo": {"enabled": bool(logo.get("enabled", True)), "motion": logo.get("motion", "pop"),
                           "has_logo": has_logo}},
        "format": {"aspect": "9:16", "resolution": "1080×1920", "fps": 30},
        "engines": ["تحلیل گفتار و کارگردان خلاق", f"موتور تدوین «{info['label']}»"] +
                   (["تصویرسازی برای بخش‌ها"] if info["pictures"] else []),
        "estimate": {"render": estimate, "paid_media": info["pictures"],
                     "note": ("تصاویر بخش‌هایی که فایل یا تصویر کتابخانه ندارند با هوش مصنوعی ساخته می‌شوند و ممکن است هزینه داشته باشند."
                              if info["pictures"] else "رندر روی سرور انجام می‌شود و هزینهٔ مدل جدیدی ندارد.")},
        "concepts": concepts,
        "style_options": [{"id": key, "label": value["label"], "summary": value["summary"], "complexity": value["complexity"]}
                          for key, value in STYLES.items()],
    }


def fingerprint(content: dict) -> str:
    """Hash of everything that affects the output; frames and estimates do not."""
    relevant = {k: v for k, v in content.items() if k not in {"estimate", "frames"}}
    return hashlib.sha256(json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def current(state: dict) -> dict | None:
    versions = (state.get("plan") or {}).get("versions") or []
    return versions[-1] if versions else None


def is_approved(state: dict) -> bool:
    version = current(state)
    return bool(version) and (state.get("plan") or {}).get("approved_id") == version["id"]


def add_version(state: dict, content: dict, *, source: str, note: str = "") -> tuple[dict, bool]:
    """Append a version if the output-relevant content changed; a new version always clears approval."""
    state = copy.deepcopy(state)
    plan = state.setdefault("plan", {"versions": [], "approved_id": None})
    latest = current(state)
    digest = fingerprint(content)
    if latest and latest["fingerprint"] == digest:
        latest["content"] = content  # refresh estimates/frames without a new version
        return state, False
    plan["versions"].append({"id": uuid.uuid4().hex, "n": len(plan["versions"]) + 1, "source": source,
                             "note": note[:300], "created_at": time.time(), "fingerprint": digest, "content": content})
    plan["versions"] = plan["versions"][-30:]
    plan["approved_id"] = None
    state["workflow"] = "awaiting_approval"
    return state, True


def approve(state: dict, version_id: str) -> dict:
    """Valid only for the current version while the project waits for approval."""
    version = current(state)
    if not version:
        raise PlanError("برنامه‌ای برای تأیید وجود ندارد.")
    if version["id"] != version_id:
        raise PlanError("این نسخهٔ برنامه دیگر جدیدترین نسخه نیست؛ نسخهٔ فعلی را بررسی و تأیید کنید.")
    if state.get("workflow") != "awaiting_approval":
        raise PlanError("این پروژه منتظر تأیید نیست.")
    state = copy.deepcopy(state)
    state["plan"]["approved_id"] = version_id
    state["plan"]["approved_at"] = time.time()
    state["workflow"] = "approved"
    return state


# -- manual plan edits ----------------------------------------------------------------------------

EDITABLE = {"hook", "hook_highlight", "look", "accent_color", "caption_font", "zoom", "key_moments",
            "logo_enabled", "logo_motion", "name", "tagline", "cta", "concept_id", "style"}


def talking_edits(content: dict, edits: dict, status: dict) -> dict:
    """Validate manual edits against what the Talking engine really supports.

    Returns {"engine": changes for talking_reel.update, "profile": brand fields to remember,
             "reanalyze": {"style", "concept"} or None, "applied": [Persian descriptions]}."""
    unknown = set(edits) - EDITABLE
    if unknown:
        raise PlanError(f"این تنظیمات در برنامه قابل ویرایش نیستند: {', '.join(sorted(unknown))}")
    import re
    style = str(status.get("style") or "talking_1")
    settings = copy.deepcopy(status.get("render_settings") or {})
    engine, profile, applied = {}, {}, []
    touched = False
    if "hook" in edits:
        text = " ".join(str(edits["hook"] or "").split())[:120]
        if not text:
            raise PlanError("هوک نمی‌تواند خالی باشد.")
        engine["hook" if style == "talking_1" else "hook2"] = text
        highlight = edits.get("hook_highlight", content["hook"]["highlight"])
        engine["hook_highlight"] = [w for w in (highlight or []) if isinstance(w, str) and w and w in text][:2]
        applied.append(f"هوک: «{text}»")
    elif "hook_highlight" in edits:
        text = content["hook"]["text"]
        engine["hook_highlight"] = [w for w in (edits["hook_highlight"] or []) if isinstance(w, str) and w and w in text][:2]
        applied.append("کلمه‌های رنگی هوک")
    if "look" in edits:
        if edits["look"] not in LOOKS:
            raise PlanError("حالت رنگ معتبر نیست.")
        settings["grade"] = dict(LOOKS[edits["look"]]["grade"]); touched = True
        applied.append(f"رنگ و نور: {LOOKS[edits['look']]['label']}")
    if "accent_color" in edits:
        colour = str(edits["accent_color"] or "").upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", colour):
            raise PlanError("رنگ تأکیدی باید به شکل ‎#RRGGBB‎ باشد.")
        settings["title_color"] = colour; profile["accent_color"] = colour; touched = True
        applied.append(f"رنگ تأکیدی {colour}")
    if "caption_font" in edits:
        if edits["caption_font"] not in FONTS:
            raise PlanError("این فونت برای کپشن پشتیبانی نمی‌شود.")
        settings["caption_font"] = edits["caption_font"]; profile["caption_font"] = edits["caption_font"]; touched = True
        applied.append(f"فونت کپشن: {FONTS[edits['caption_font']]}")
    if "zoom" in edits:
        try:
            amount = max(0, min(200, int(edits["zoom"])))
        except (TypeError, ValueError):
            raise PlanError("میزان زوم باید عدد باشد.")
        settings.setdefault("zoom", {})["amount"] = amount; touched = True
        applied.append(f"زوم {amount}٪")
    if "key_moments" in edits:
        settings["key_moments_enabled"] = bool(edits["key_moments"]); touched = True
        applied.append("لحظه‌های کلیدی " + ("روشن" if edits["key_moments"] else "خاموش"))
    if "logo_enabled" in edits or "logo_motion" in edits:
        logo = dict(settings.get("outro_logo") or {"enabled": True, "motion": "pop"})
        if "logo_enabled" in edits:
            logo["enabled"] = bool(edits["logo_enabled"])
        if "logo_motion" in edits:
            if edits["logo_motion"] not in {"pop", "fade", "slide"}:
                raise PlanError("حرکت لوگو معتبر نیست.")
            logo["motion"] = edits["logo_motion"]; profile["logo_motion"] = edits["logo_motion"]
        if not logo["enabled"]:
            logo["motion"] = "none"
        elif logo.get("motion") == "none":
            logo["motion"] = "pop"
        settings["outro_logo"] = logo; touched = True
        applied.append("لوگوی پایانی " + ("روشن" if logo["enabled"] else "خاموش"))
    for field, key, label in (("name", "name", "نام گوینده"), ("tagline", "title", "تگ‌لاین"), ("cta", "cta", "دعوت به اقدام")):
        if field in edits:
            value = " ".join(str(edits[field] or "").split())[:120]
            engine[key] = value; profile[field] = value
            applied.append(f"{label}: «{value}»" if value else f"{label} حذف شد")
    if touched:
        engine["render_settings"] = settings
    reanalyze = None
    if "concept_id" in edits:
        concept = next((c for c in content.get("concepts") or [] if c.get("id") == edits["concept_id"]), None)
        if concept is None:
            raise PlanError("این ایده در برنامه پیدا نشد.")
        if not concept.get("selected"):
            reanalyze = {"style": edits.get("style") if edits.get("style") in STYLES else concept["style"],
                         "concept_id": concept["id"]}
            applied.append(f"ایدهٔ «{concept['name']}» با سبک {STYLES[reanalyze['style']]['label']}")
    elif "style" in edits:
        if edits["style"] not in STYLES:
            raise PlanError("این سبک وجود ندارد.")
        if edits["style"] != style:
            reanalyze = {"style": edits["style"], "concept_id": None}
            applied.append(f"سبک تدوین: {STYLES[edits['style']]['label']}")
    return {"engine": engine, "profile": profile, "reanalyze": reanalyze, "applied": applied}


def summary_text(content: dict, version: dict) -> str:
    """Short chat message for a new plan version; the full plan is at the top of the Edit tab."""
    hook = content["hook"]["text"]
    lines = [f"برنامهٔ تدوین آماده است (نسخهٔ {version['n']}).",
             f"• ایده: {content['concept']['name'] or '—'}" + (f" — {content['concept']['angle']}" if content['concept']['angle'] else ""),
             f"• سبک: {content['style']['label']} ({content['style']['complexity']})",
             f"• هوک: «{hook}»" if hook else "",
             f"• رنگ تأکیدی {content['look']['accent_color']} · {LOOKS.get(content['look']['preset'], {}).get('label', 'رنگ سفارشی')}"]
    render = (content.get("estimate") or {}).get("render")
    if render:
        lines.append(f"• زمان رندر تخمینی: {round(render['low_s'] / 60, 1)} تا {round(render['high_s'] / 60, 1)} دقیقه")
    lines.append("\nبرنامه را در تب «Edit» ببینید؛ هر بخش را عوض کنید یا همین‌جا بنویسید چه تغییری بدهم. رندر فقط بعد از تأیید شما شروع می‌شود.")
    return "\n".join(line for line in lines if line)

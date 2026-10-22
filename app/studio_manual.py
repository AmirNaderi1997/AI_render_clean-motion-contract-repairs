"""Persisted human-in-the-loop checkpoints. Never an independent video pipeline."""
from __future__ import annotations

import copy
import json
import uuid

from app.studio_store import repo, run


def choice(value, label, description="", **visual):
    return {"value": value, "label": label, "description": description, **visual}


def steps(engine):
    common = [
        {"key": "reference", "title": "رفرنس سبک دارید؟", "description": "عکس یا ویدیو را با دکمهٔ + پیوست کنید و توضیح بدهید کدام ویژگی را می‌خواهید. رفرنس منبع اصلی را عوض نمی‌کند. تطابق پیکسلی تضمین نمی‌شود.",
         "choices": [choice("skip", "بدون رفرنس"), choice("attached", "تحلیل رفرنس پیوست‌شده")], "input": True},
        {"key": "analyze", "title": "تحلیل و طراحی برنامه شروع شود؟", "description": "گفتار/منابع و رفرنس بررسی و برنامه طراحی می‌شود؛ این مرحله ممکن است هزینهٔ مدل داشته باشد. هنوز رندر یا تولید مدیا شروع نمی‌شود.",
         "choices": [choice("approve", "تأیید و شروع تحلیل")], "input": False},
    ]
    if engine == "talking":
        from engine.talking_reel import style_list
        return [
            {"key": "style", "title": "کدام نوع تدوین صحبتی؟", "input": False,
             "choices": [choice(s["id"], s["label"], layout=s["id"]) for s in style_list()]},
            {"key": "look", "title": "نور و رنگ تصویر", "input": False,
             "choices": [choice("natural", "طبیعی", "رنگ و نور نزدیک به منبع", swatch="#C8BBA6"), choice("warm", "گرم", "کمی گرم‌تر و پرکنتراست", swatch="#C19670"), choice("cool", "سرد و ملایم", swatch="#8998A6")]},
            {"key": "font", "title": "فونت زیرنویس", "input": False,
             "choices": [choice("default", "فونت اصلی سبک", "Ray؛ حفظ تایپوگرافی سبک"), choice("Vazirmatn", "وزیرمتن", "زیرنویس فارسی ساده و خوانا", font="Vazirmatn")]},
            {"key": "color", "title": "رنگ تأکید تیتر", "input": False,
             "choices": [choice("#F5B800", "طلایی", swatch="#F5B800"), choice("#FFFFFF", "سفید", swatch="#FFFFFF"), choice("#A8CF80", "سبز", swatch="#A8CF80")]},
            {"key": "logo", "title": "لوگو موشن پایان", "description": "از لوگوی فعلی پروژه استفاده می‌شود؛ انتخاب خاموش، لوگوی CTA را هم خاموش می‌کند.", "input": False,
             "choices": [choice("off", "بدون لوگو"), choice("pop", "نمایش پاپ"), choice("fade", "محو تدریجی"), choice("slide", "حرکت نرم")]},
            {"key": "logo_asset", "title": "فایل لوگو", "description": "اگر لوگو را فعال کردید، می‌توانید یک PNG یا تصویر لوگو پیوست کنید. ویدیوی منبع جایگزین نمی‌شود.", "input": False,
             "choices": [choice("existing", "لوگوی فعلی"), choice("attached", "استفاده از تصویر پیوست")]},
            {"key": "logo_color", "title": "رنگ لوگو", "description": "در حالت بدون لوگو، این انتخاب اثری ندارد. رنگ تک‌رنگ، شفافیت تصویر را حفظ می‌کند.", "input": False,
             "choices": [choice("original", "رنگ اصلی"), choice("#FFFFFF", "سفید", swatch="#FFFFFF"), choice("#000000", "مشکی", swatch="#000000")]},
            {"key": "cta", "title": "متن دعوت به اقدام پایانی", "description": "متن دقیق را همین‌جا بنویسید یا بدون CTA ادامه بدهید.", "input": True,
             "choices": [choice("none", "بدون CTA")]},
        ] + common
    if engine == "localize":
        from engine.localize import BOX_STYLES
        return [{"key": "caption_box", "title": "قاب زیرنویس فارسی", "input": False,
                 "choices": [choice(k, str(k)) for k in BOX_STYLES]},
                {"key": "end_card", "title": "کارت پایان داشته باشد؟", "input": False,
                 "choices": [choice("off", "بدون کارت پایان"), choice("on", "کارت پایان فعلی")]}] + common[-1:]
    return [{"key": "direction", "title": "زبان بصری ویدیو", "input": True,
             "description": "رنگ، نور، کنوس، تایپوگرافی و لحن دلخواه را توضیح بدهید. فقط قابلیت‌های قابل‌اجرای موتور در برنامه پذیرفته می‌شوند.",
             "choices": [choice("minimal", "مینیمال", "تایپوگرافی خوانا و فضای خلوت"), choice("editorial", "روایی", "صحنه‌های مفهومی متناسب با روایت"), choice("brand", "برند محصول", "بر اساس تصاویر واقعی محصول")]}] + common


def question(session):
    spec = steps(session["engine"])[session["index"]]
    return {**spec, "id": session["question_id"], "engine": session["engine"]}


def save(cid, user, session):
    conversation = run(repo.get_conversation(cid, user))
    run(repo.set_conversation(cid, user, state={**conversation.get("state", {}), "manual_session": session}))
    if session and session.get("question_id"):
        run(repo.emit(cid, "question.required", {"kind": "manual", "question": question(session)["title"]}))


def begin(cid, user, engine, text, attachment_ids):
    session = {"id": uuid.uuid4().hex, "engine": engine, "text": text,
               "attachment_ids": attachment_ids, "reference_ids": [], "answers": {}, "index": 0,
               "question_id": uuid.uuid4().hex}
    save(cid, user, session)
    return session


def answer(cid, user, session, response, text, attachment_ids):
    """Validate the exact live question, never interpret stale card clicks as a new edit."""
    if response != session["question_id"]:
        raise ValueError("این سؤال دیگر فعال نیست؛ انتخاب فعلی چت را پاسخ بدهید.")
    spec = steps(session["engine"])[session["index"]]
    value = text.strip()
    if spec['key'] == 'logo_asset' and attachment_ids and value not in {'existing', 'attached'}:
        value = 'attached'
    values = {c["value"] for c in spec["choices"]}
    if value not in values and not spec.get("input"):
        raise ValueError("یکی از گزینه‌های همین مرحله را انتخاب کنید.")
    result = copy.deepcopy(session)
    if spec["key"] == "reference" and value != "skip":
        owned = run(repo.get_attachments(attachment_ids, cid, user))
        if not owned or any(a["kind"] not in {"image", "video"} for a in owned):
            raise ValueError("برای رفرنس یک عکس یا ویدیو پیوست کنید؛ فایل اصلی پروژه حفظ شده است.")
        result["reference_ids"] = attachment_ids
    if spec['key'] == 'logo_asset' and value == 'attached':
        owned = run(repo.get_attachments(attachment_ids, cid, user))
        if len(owned) != 1 or owned[0]['kind'] != 'image':
            raise ValueError('یک تصویر لوگو پیوست کنید.')
        result['logo_attachment_id'] = owned[0]['id']
    if not run(repo.claim_manual_question(cid, user, response)):
        raise ValueError('این پاسخ قبلاً ثبت شده است؛ درخواست تکراری اجرا نشد.')
    result.pop('claimed', None)
    result["answers"][spec["key"]] = value[:2000]
    result["index"] += 1
    result["question_id"] = uuid.uuid4().hex if result["index"] < len(steps(result["engine"])) else None
    save(cid, user, result)
    return result


def request_notes(session):
    return session["text"] + "\nUser-approved manual direction (do not invent unsupported settings):\n" + json.dumps(session["answers"], ensure_ascii=False)


def talking_changes(answers, current):
    settings = copy.deepcopy(current.get("render_settings") or {})
    grades = {"natural": {"brightness": 0, "contrast": 100, "saturation": 100, "temperature": 0, "vignette": 0},
              "warm": {"brightness": 0, "contrast": 108, "saturation": 100, "temperature": 12, "vignette": 20},
              "cool": {"brightness": 0, "contrast": 104, "saturation": 92, "temperature": -10, "vignette": 15}}
    if answers.get("look") in grades: settings["grade"] = grades[answers["look"]]
    if answers.get("font"): settings["caption_font"] = answers["font"]
    if answers.get("color"): settings["title_color"] = answers["color"]
    if answers.get("logo"):
        settings["outro_logo"] = {"enabled": answers["logo"] != "off", "motion": answers["logo"] if answers["logo"] != "off" else "none"}
    return {"render_settings": settings, "cta": "" if answers.get("cta") == "none" else answers.get("cta", current.get("cta", ""))}


def apply_talking_preferences(cid, user, project, job, status):
    from pathlib import Path
    from PIL import Image
    from app import talking_reel
    answers = project['state'].get('manual_answers', {})
    talking_reel.update(job.dir, talking_changes(answers, status))
    aid = project['state'].get('manual_logo_attachment_id')
    tint = answers.get('logo_color')
    if aid or tint in {'#FFFFFF', '#000000'}:
        source = Path(run(repo.get_attachments([aid], cid, user))[0]['path']) if aid else talking_reel.custom_logo(job.dir)
        source = source or Path(__file__).resolve().parents[1] / 'assets' / 'brand' / 'logo.png'
        with Image.open(source) as image:
            image = image.convert('RGBA'); image.thumbnail((1600, 1600))
            if tint in {'#FFFFFF', '#000000'}:
                replacement = Image.new('RGBA', image.size, tint)
                replacement.putalpha(image.getchannel('A')); image = replacement
            image.save(job.dir / 'talking_reel_logo.png')


async def render_checkpoint(conversation_id, user_key, project, summary):
    """Idempotent persisted gate, including after refresh/reconnect. No execution here."""
    state = project["state"]
    if state.get("manual_render_approved"): return False
    if not state.get("manual_checkpoint"):
        state = {**state, "manual_checkpoint": {"id": uuid.uuid4().hex, "title": "برنامه آماده است؛ مرحلهٔ بعد اجرا شود؟",
                 "summary": summary, "choices": [choice("approve", "تأیید و ادامه"), choice("edit", "اصلاح برنامه") ]}}
        await repo.update_project(project["id"], user_key, state=state, status="awaiting_confirmation")
        await repo.emit(conversation_id, "question.required", {"kind": "manual", "project_id": project["id"], "question": "برنامه را بررسی و تأیید کنید."}, source_event_id=f"manual-review:{state['manual_checkpoint']['id']}")
    return True

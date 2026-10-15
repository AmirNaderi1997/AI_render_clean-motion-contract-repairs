"""Generate deterministic HyperFrames projects from approved visual beats."""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from .schema import VisualBeat

ROOT = Path(__file__).resolve().parents[2]
RAY = ROOT / "presets" / "fonts" / "RAY-EXTRABOLD.TTF"


VISUAL_TYPES = {"concept", "stat", "comparison", "steps", "ui_showcase", "media_collage",
                "chat", "map_route", "spec_callout", "kinetic_type", "before_after"}


def _visual_type(title: str, items: list[str], requested: str = "") -> str:
    if requested in VISUAL_TYPES and requested != "concept":
        return requested
    if len(items) >= 2:
        return "steps"
    if re.search(r"[۰-۹0-9٪%]", title):
        return "stat"
    if any(token in title for token in ("مقایسه", "در برابر", "یا ", "قبل", "بعد")):
        return "comparison"
    return "concept"


def build_visual_beats(plan, decisions: dict) -> list[VisualBeat]:
    """Map source-sentence decisions onto the cut output timeline."""
    chips = {int(item["i"]): list(item.get("items") or []) for item in decisions.get("chips") or []}
    beats: list[VisualBeat] = []
    for n, item in enumerate(decisions.get("broll") or []):
        sentence = int(item["i"])
        shots = [shot for shot in plan.shots if shot.slot == sentence]
        if not shots:
            continue
        start = min(float(shot.out_start) for shot in shots)
        end = max(float(shot.out_start + shot.length) for shot in shots)
        if end - start < 0.65:
            continue
        title = " ".join(str(item.get("label") or "").split())[:80]
        if not title:
            title = " ".join(str(item.get("visual") or "").split()[:5]) or "نکته مهم"
        raw_items = list(item.get("items") or []) or chips.get(sentence, [])
        values = [" ".join(str(value).split())[:35] for value in raw_items if str(value).strip()]
        beats.append(VisualBeat(
            id=f"beat-{sentence}-{n}", start=start, end=end,
            anchor_word=title.split()[0], visual_type=_visual_type(title, values, str(item.get("visual_type") or "")),
            title=title, items=values, accent="amber" if n % 2 else "teal",
        ))
    return beats


def _beat_markup(beat: VisualBeat) -> str:
    title = html.escape(beat.title)
    if beat.visual_type == "steps" and beat.items:
        body = "".join(
            f'<div class="step"><b>{i + 1:02d}</b><span>{html.escape(value)}</span></div>'
            for i, value in enumerate(beat.items)
        )
    elif beat.visual_type == "comparison":
        body = '<div class="compare"><span>قبل</span><i></i><span>بعد</span></div>'
    elif beat.visual_type == "stat":
        match = re.search(r"[۰-۹0-9]+(?:[٫.][۰-۹0-9]+)?(?:\s*[٪%×x])?", beat.title)
        value = html.escape(match.group(0) if match else beat.title.split()[0])
        body = f'<div class="stat">{value}</div><div class="meter"><i></i></div>'
    elif beat.visual_type == "ui_showcase":
        body = '<div class="ui-stage"><i></i><i></i><i></i><span></span></div>'
    elif beat.visual_type == "media_collage":
        body = '<div class="collage"><i></i><i></i><i></i><i></i></div>'
    elif beat.visual_type == "chat":
        values = beat.items or ["سؤال دقیق", "پاسخ روشن"]
        body = '<div class="chat-stack">' + ''.join(
            f'<span class="bubble b{n % 2}">{html.escape(value)}</span>' for n, value in enumerate(values[:3])
        ) + '</div>'
    elif beat.visual_type == "map_route":
        body = '<div class="route"><svg viewBox="0 0 800 260"><path d="M70 190 C220 30 410 245 720 65"/><circle cx="70" cy="190" r="18"/><circle cx="720" cy="65" r="18"/></svg></div>'
    elif beat.visual_type == "spec_callout":
        values = beat.items or ["سریع", "دقیق", "ساده"]
        body = '<div class="specs">' + ''.join(
            f'<span><b>{i + 1:02d}</b>{html.escape(value)}</span>' for i, value in enumerate(values[:3])
        ) + '</div>'
    elif beat.visual_type == "kinetic_type":
        body = f'<div class="kinetic" dir="rtl">{title}</div>'
    elif beat.visual_type == "before_after":
        body = '<div class="before-after"><span>قبل</span><i></i><span>بعد</span></div>'
    else:
        body = '<div class="concept"><i></i><i></i><i></i><span></span></div>'
    return (
        f'<section id="{beat.id}" class="visual-beat {beat.visual_type} {beat.accent} clip" '
        f'data-start="{beat.start:.3f}" data-duration="{beat.end - beat.start:.3f}" data-track-index="2">'
        f'<div class="beat-inner"><div class="eyebrow">نکته‌ی کلیدی</div><h2 dir="rtl">{title}</h2>{body}</div></section>'
    )


def _timeline_script(beats: list[VisualBeat]) -> str:
    lines = ['const tl = gsap.timeline({ paused: true });']
    for beat in beats:
        duration = beat.end - beat.start
        selector = f"#{beat.id} .beat-inner"
        lines.append(
            f'tl.fromTo("{selector}", {{opacity:0,y:-22,scale:.97}}, '
            f'{{opacity:1,y:0,scale:1,duration:.32,ease:"power2.out"}}, {beat.start:.3f});'
        )
        lines.append(
            f'tl.to("{selector}", {{opacity:0,y:-10,duration:.22,ease:"power1.in"}}, '
            f'{max(beat.start + .4, beat.end - .22):.3f});'
        )
        if beat.visual_type == "stat":
            lines.append(
                f'tl.fromTo("#{beat.id} .meter i", {{scaleX:0}}, '
                f'{{scaleX:1,duration:{min(1.0, duration * .45):.3f},ease:"power2.out"}}, {beat.start + .18:.3f});'
            )
        elif beat.visual_type in {"steps", "chat", "spec_callout"}:
            child = ".step" if beat.visual_type == "steps" else (".bubble" if beat.visual_type == "chat" else ".specs span")
            lines.append(
                f'tl.fromTo("#{beat.id} {child}", {{opacity:0,y:28}}, '
                f'{{opacity:1,y:0,duration:.28,stagger:.09,ease:"power2.out"}}, {beat.start + .16:.3f});'
            )
        elif beat.visual_type in {"ui_showcase", "media_collage"}:
            child = ".ui-stage i" if beat.visual_type == "ui_showcase" else ".collage i"
            lines.append(
                f'tl.fromTo("#{beat.id} {child}", {{opacity:0}}, '
                f'{{opacity:1,duration:.32,stagger:.08,ease:"power1.out"}}, {beat.start + .14:.3f});'
            )
        elif beat.visual_type == "map_route":
            lines.append(
                f'tl.fromTo("#{beat.id} .route path", {{strokeDashoffset:420}}, '
                f'{{strokeDashoffset:0,duration:{min(1.2, duration * .55):.3f},ease:"power1.inOut"}}, {beat.start + .15:.3f});'
            )
        elif beat.visual_type == "kinetic_type":
            lines.append(
                f'tl.fromTo("#{beat.id} .kinetic", {{scale:.72,rotation:-2}}, '
                f'{{scale:1,rotation:0,duration:.38,ease:"back.out(1.7)"}}, {beat.start + .12:.3f});'
            )
        elif beat.visual_type == "before_after":
            lines.append(
                f'tl.fromTo("#{beat.id} .before-after i", {{scaleY:0}}, '
                f'{{scaleY:1,duration:.4,ease:"power3.out"}}, {beat.start + .15:.3f});'
            )
    lines.extend(['window.__timelines = window.__timelines || {};', 'window.__timelines["main"] = tl;', 'tl.seek(0);'])
    return "\n".join(lines)


def build_project(project_dir: Path, base_video: Path, beats: list[VisualBeat], *, duration: float) -> Path:
    """Write a self-contained 1080x1920 HyperFrames composition."""
    project_dir.mkdir(parents=True, exist_ok=True)
    assets = project_dir / "assets"
    assets.mkdir(exist_ok=True)
    video = assets / "base.mp4"
    if video.exists() or video.is_symlink():
        video.unlink()
    try:
        video.symlink_to(base_video.resolve())
    except OSError:
        shutil.copy2(base_video, video)
    shutil.copy2(RAY, assets / "ray-extrabold.ttf")
    metadata = {"id": "ai-render-talking-2", "name": "AI Render Talking 2"}
    (project_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "media": {"autoProxy": True},
    }, indent=2))
    cards = "\n".join(_beat_markup(beat) for beat in beats)
    document = f'''<!doctype html>
<html lang="fa"><head><meta charset="UTF-8"><meta name="viewport" content="width=1080,height=1920">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face{{font-family:Ray;src:url('./assets/ray-extrabold.ttf')}}
*{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#080b0c}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;font-family:Ray,sans-serif}}
.base{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.visual-beat{{position:absolute;left:46px;right:46px;top:82px;height:760px;padding:62px 58px;border-radius:42px;overflow:hidden;
background:#f3f0e8;color:#151a1b;box-shadow:0 28px 80px #0007;direction:rtl}}
.beat-inner{{position:absolute;inset:0;padding:62px 58px;opacity:0}}
.visual-beat:after{{content:"";position:absolute;inset:0;border:2px solid #ffffff80;border-radius:42px;pointer-events:none}}
.eyebrow{{font-size:29px;color:#5a6263;margin-bottom:25px}}h2{{font-size:66px;line-height:1.28;margin:0;max-width:870px;letter-spacing:-.02em}}
.teal{{--accent:#157a7b}}.amber{{--accent:#c77a25}}.stat{{font-size:150px;color:var(--accent);margin-top:58px;line-height:1}}
.meter{{height:18px;background:#d8d4ca;border-radius:12px;margin-top:34px;overflow:hidden;direction:ltr}}.meter i{{display:block;width:78%;height:100%;background:var(--accent);transform-origin:left}}
.step{{display:flex;align-items:center;gap:24px;margin-top:27px;font-size:40px}}.step b{{display:grid;place-items:center;width:72px;height:72px;border-radius:22px;background:var(--accent);color:white;font-size:28px}}.step span{{border-bottom:2px solid #151a1b20;padding:10px 0;flex:1}}
.compare{{display:flex;align-items:center;justify-content:space-between;margin-top:105px;font-size:62px;color:var(--accent)}}.compare i{{width:210px;height:4px;background:var(--accent);position:relative}}.compare i:after{{content:"";position:absolute;right:0;top:-11px;border:13px solid transparent;border-left:0;border-right-color:var(--accent)}}
.concept{{height:320px;position:relative;margin-top:40px}}.concept i{{position:absolute;width:110px;height:110px;border-radius:50%;border:16px solid var(--accent)}}.concept i:nth-child(1){{right:40px;top:80px}}.concept i:nth-child(2){{right:310px;top:10px}}.concept i:nth-child(3){{right:565px;top:120px}}.concept span{{position:absolute;right:140px;top:135px;width:510px;height:5px;background:var(--accent);transform:rotate(-4deg);transform-origin:right}}
.ui-stage{{position:relative;height:360px;margin-top:28px;perspective:900px}}.ui-stage i{{position:absolute;width:250px;height:300px;border-radius:26px;background:#171c1d;border:4px solid #fff;box-shadow:0 24px 45px #0005}}.ui-stage i:nth-child(1){{right:70px;transform:rotate(7deg)}}.ui-stage i:nth-child(2){{right:320px;top:22px;transform:scale(1.08)}}.ui-stage i:nth-child(3){{right:570px;transform:rotate(-7deg)}}.ui-stage span{{position:absolute;right:365px;top:75px;width:160px;height:16px;background:var(--accent);box-shadow:0 45px #ffffff30,0 90px #ffffff30}}
.collage{{position:relative;height:340px;margin-top:28px}}.collage i{{position:absolute;width:255px;height:190px;border-radius:22px;background:#202627;border:4px solid #fff;box-shadow:0 22px 35px #0004}}.collage i:nth-child(1){{right:40px;top:20px;transform:rotate(6deg)}}.collage i:nth-child(2){{right:245px;top:100px;transform:rotate(-5deg)}}.collage i:nth-child(3){{right:455px;top:5px;transform:rotate(4deg)}}.collage i:nth-child(4){{right:640px;top:120px;transform:rotate(-7deg)}}
.chat-stack{{display:flex;flex-direction:column;gap:18px;margin-top:40px}}.bubble{{max-width:72%;padding:20px 28px;border-radius:28px;font-size:34px}}.bubble.b0{{align-self:flex-start;background:#e1ddd3}}.bubble.b1{{align-self:flex-end;background:var(--accent);color:#fff}}
.route{{height:300px;margin-top:25px}}.route svg{{width:100%;height:100%;overflow:visible}}.route path{{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round;stroke-dasharray:22 22}}.route circle{{fill:#f3f0e8;stroke:var(--accent);stroke-width:12}}
.specs{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:48px}}.specs span{{display:flex;flex-direction:column;gap:18px;padding:26px 18px;border:3px solid #151a1b;border-radius:24px;font-size:29px}}.specs b{{font-size:48px;color:var(--accent)}}
.kinetic{{font-size:118px;line-height:1;margin-top:55px;color:var(--accent);max-width:900px;overflow:hidden}}
.before-after{{display:grid;grid-template-columns:1fr 10px 1fr;gap:20px;align-items:center;margin-top:75px;font-size:70px;text-align:center}}.before-after i{{height:210px;background:var(--accent);border-radius:9px}}
</style></head><body><main id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="1080" data-height="1920">
<video id="rough-cut" class="base clip" src="./assets/base.mp4" data-start="0" data-duration="{duration:.3f}" data-track-index="0" data-has-audio="true"></video>
{cards}</main><script>{_timeline_script(beats)}</script></body></html>'''
    entry = project_dir / "index.html"
    entry.write_text(document)
    return entry

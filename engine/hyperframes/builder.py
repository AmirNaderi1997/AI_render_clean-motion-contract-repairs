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


def _visual_type(title: str, items: list[str]) -> str:
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
        values = [" ".join(str(value).split())[:35] for value in chips.get(sentence, []) if str(value).strip()]
        beats.append(VisualBeat(
            id=f"beat-{sentence}-{n}", start=start, end=end,
            anchor_word=title.split()[0], visual_type=_visual_type(title, values),
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
    else:
        body = '<div class="concept"><i></i><i></i><i></i><span></span></div>'
    return (
        f'<section id="{beat.id}" class="visual-beat {beat.visual_type} {beat.accent} clip" '
        f'data-start="{beat.start:.3f}" data-duration="{beat.end - beat.start:.3f}" data-track-index="2">'
        f'<div class="eyebrow">نکته‌ی کلیدی</div><h2 dir="rtl">{title}</h2>{body}</section>'
    )


def _timeline_script(beats: list[VisualBeat]) -> str:
    lines = ['const tl = gsap.timeline({ paused: true });']
    for beat in beats:
        duration = beat.end - beat.start
        selector = f"#{beat.id}"
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
                f'tl.fromTo("{selector} .meter i", {{scaleX:0}}, '
                f'{{scaleX:1,duration:{min(1.0, duration * .45):.3f},ease:"power2.out"}}, {beat.start + .18:.3f});'
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
#root{{position:relative;width:1080px;height:1920px;overflow:hidden;font-family:Ray,sans-serif}}
.base{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.visual-beat{{position:absolute;left:46px;right:46px;top:82px;height:760px;padding:62px 58px;border-radius:42px;overflow:hidden;
background:#f3f0e8;color:#151a1b;box-shadow:0 28px 80px #0007;opacity:0;direction:rtl}}
.visual-beat:after{{content:"";position:absolute;inset:0;border:2px solid #ffffff80;border-radius:42px;pointer-events:none}}
.eyebrow{{font-size:29px;color:#5a6263;margin-bottom:25px}}h2{{font-size:66px;line-height:1.28;margin:0;max-width:870px;letter-spacing:-.02em}}
.teal{{--accent:#157a7b}}.amber{{--accent:#c77a25}}.stat{{font-size:150px;color:var(--accent);margin-top:58px;line-height:1}}
.meter{{height:18px;background:#d8d4ca;border-radius:12px;margin-top:34px;overflow:hidden;direction:ltr}}.meter i{{display:block;width:78%;height:100%;background:var(--accent);transform-origin:left}}
.step{{display:flex;align-items:center;gap:24px;margin-top:27px;font-size:40px}}.step b{{display:grid;place-items:center;width:72px;height:72px;border-radius:22px;background:var(--accent);color:white;font-size:28px}}.step span{{border-bottom:2px solid #151a1b20;padding:10px 0;flex:1}}
.compare{{display:flex;align-items:center;justify-content:space-between;margin-top:105px;font-size:62px;color:var(--accent)}}.compare i{{width:210px;height:4px;background:var(--accent);position:relative}}.compare i:after{{content:"";position:absolute;right:0;top:-11px;border:13px solid transparent;border-left:0;border-right-color:var(--accent)}}
.concept{{height:320px;position:relative;margin-top:40px}}.concept i{{position:absolute;width:110px;height:110px;border-radius:50%;border:16px solid var(--accent)}}.concept i:nth-child(1){{right:40px;top:80px}}.concept i:nth-child(2){{right:310px;top:10px}}.concept i:nth-child(3){{right:565px;top:120px}}.concept span{{position:absolute;right:140px;top:135px;width:510px;height:5px;background:var(--accent);transform:rotate(-4deg);transform-origin:right}}
</style></head><body><main id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="1080" data-height="1920">
<video id="rough-cut" class="base clip" src="./assets/base.mp4" data-start="0" data-duration="{duration:.3f}" data-track-index="0" data-has-audio="true"></video>
{cards}</main><script>{_timeline_script(beats)}</script></body></html>'''
    entry = project_dir / "index.html"
    entry.write_text(document)
    return entry

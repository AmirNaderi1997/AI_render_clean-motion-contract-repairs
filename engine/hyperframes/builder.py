"""Generate deterministic HyperFrames projects from approved visual beats."""
from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from .schema import VisualBeat
from .catalog import recommend

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
    """Turn the approved storyboard into short, varied output-time worlds.

    Story beats deliberately do not inherit sentence duration: Persian speech
    transcripts often contain one enormous sentence, which used to produce one
    enormous card.  Every catalog item is scored for every beat; selected
    references are unique until the suitable pool is exhausted.
    """
    chips = {int(item["i"]): list(item.get("items") or []) for item in decisions.get("chips") or []}
    storyboard = list(decisions.get("storyboard") or [])
    if not storyboard:
        storyboard = [{**item, "title": item.get("label") or item.get("visual") or "نکته مهم"}
                      for item in decisions.get("broll") or []]
    duration = float(getattr(plan, "duration", 0) or 0)
    if not storyboard or duration < 1:
        return []
    count = min(6, max(5, len(storyboard)))
    storyboard = (storyboard * ((count + len(storyboard) - 1) // len(storyboard)))[:count]
    # Keep room for the speaker between worlds. The first visual starts after
    # the hook and each scene is capped to avoid the old permanent-list look.
    usable_start = min(3.0, duration * .08)
    step = max(3.1, (duration - usable_start - 1.0) / count)
    used_refs: set[str] = set()
    fallback_types = ["kinetic_type", "concept", "comparison", "media_collage", "ui_showcase", "stat", "chat", "before_after"]
    fallback_motions = ["slam", "assemble", "wipe", "collage", "orbit", "count_up", "type_on", "reveal"]
    beats: list[VisualBeat] = []
    for n, item in enumerate(storyboard):
        sentence = int(item["i"])
        start = usable_start + n * step
        scene_duration = min(4.8, max(2.35, step * .72))
        end = min(duration - .35, start + scene_duration)
        title = " ".join(str(item.get("title") or item.get("label") or "").split())[:80]
        if not title:
            title = " ".join(str(item.get("visual") or "").split()[:5]) or "نکته مهم"
        broll_item = next((value for value in decisions.get("broll") or [] if int(value.get("i", -1)) == sentence), {})
        raw_items = list(item.get("items") or []) or chips.get(sentence, []) or list(broll_item.get("items") or [])
        values = [" ".join(str(value).split())[:35] for value in raw_items if str(value).strip()]
        visual_type = _visual_type(title, values, str(item.get("visual_type") or ""))
        if visual_type == "stat" and not re.search(r"[۰-۹0-9٪%]", title + " " + " ".join(values)):
            visual_type = "concept"
        if visual_type == "before_after" and (" یا " in title or set(values) & {"محصول فیزیکی", "محصول دیجیتال"}):
            visual_type = "comparison"
        if beats and visual_type == beats[-1].visual_type:
            visual_type = fallback_types[n % len(fallback_types)]
        motion_style = str(item.get("motion_style") or fallback_motions[n % len(fallback_motions)])
        if beats and motion_style == beats[-1].motion_style:
            motion_style = fallback_motions[n % len(fallback_motions)]
        # Catalog search informs the choreography vocabulary, but a reference
        # is recorded only when its actual registry code is installed/wired.
        refs: list[str] = []
        beats.append(VisualBeat(
            id=f"beat-{sentence}-{n}", start=start, end=end,
            anchor_word=title.split()[0], visual_type=visual_type,
            title=title, items=values, accent=("teal", "coral", "blue", "amber", "ink")[n % 5],
            layout="full_frame" if n in {0, 3, count - 1} else "top_panel",
            registry_refs=refs,
            narrative_role=str(item.get("narrative_role") or "evidence"),
            motion_style=motion_style,
            why=str(item.get("why") or ""),
        ))
    return beats


def _beat_markup(beat: VisualBeat) -> str:
    title = html.escape(beat.title)
    if beat.registry_refs and beat.registry_refs[0] == "hw-pipeline":
        body = (f'<div class="registry-stage"><div data-composition-id="hw-pipeline" '
                f'data-composition-src="compositions/hw-pipeline.html" data-start="0" data-duration="{beat.end - beat.start:.3f}" '
                'data-width="1920" data-height="1080" data-track-index="0"></div></div>')
    elif beat.visual_type == "steps" and beat.items:
        body = "".join(
            f'<div class="step"><b>{i + 1:02d}</b><span>{html.escape(value)}</span></div>'
            for i, value in enumerate(beat.items)
        )
    elif beat.visual_type == "comparison":
        labels = beat.items[:2] or [value.strip() for value in re.split(r"(?:در برابر| یا )", beat.title) if value.strip()][:2]
        labels = (labels + ["خدمت", "محصول"])[:2]
        body = (f'<div class="compare"><div><strong>×۱</strong><span>{html.escape(labels[0])}</span></div>'
                f'<i><b>→</b></i><div><strong>×∞</strong><span>{html.escape(labels[1])}</span></div></div>')
    elif beat.visual_type == "stat":
        match = re.search(r"[۰-۹0-9]+(?:[٫.][۰-۹0-9]+)?(?:\s*[٪%×x])?", beat.title)
        value = html.escape(match.group(0) if match else beat.title.split()[0])
        body = f'<div class="stat">{value}</div><div class="meter"><i></i></div>'
    elif beat.visual_type == "ui_showcase":
        body = '<div class="ui-stage"><i></i><i></i><i></i><span></span></div>'
    elif beat.visual_type == "media_collage":
        values = beat.items or ["گوشی", "دوره آموزشی", "پادکست", "نرم‌افزار"]
        glyphs = ["▣", "▶", "◉", "⌁"]
        body = '<div class="collage">' + ''.join(
            f'<div><b>{glyphs[n % 4]}</b><span>{html.escape(value)}</span></div>' for n, value in enumerate(values[:4])
        ) + '</div>'
    elif beat.visual_type == "chat":
        values = beat.items or ["سؤال دقیق", "پاسخ روشن"]
        body = '<div class="chat-stack">' + ''.join(
            f'<span class="bubble b{n % 2}">{html.escape(value)}</span>' for n, value in enumerate(values[:3])
        ) + '</div>'
    elif beat.visual_type == "map_route":
        body = '<div class="route"><svg viewBox="0 0 800 260"><path d="M70 190 C220 30 410 245 720 65"/><circle cx="70" cy="190" r="18"/><circle cx="720" cy="65" r="18"/></svg></div>'
    elif beat.visual_type == "spec_callout":
        values = beat.items or ["Software", "as a", "Service"]
        body = '<div class="saas-mark"><b>S</b><i></i><div>' + ''.join(
            f'<span>{html.escape(value)}</span>' for value in values[:3]
        ) + '</div></div>'
    elif beat.visual_type == "kinetic_type":
        body = f'<div class="kinetic" dir="rtl">{title}</div>'
    elif beat.visual_type == "before_after":
        values = [re.sub(r"^(?:قبل|بعد)\s*[:：-]?\s*", "", value).strip() for value in beat.items[:2]]
        values = (values + ["خودت خدمت می‌دهی", "نرم‌افزار می‌فروشد"])[:2]
        body = f'<div class="before-after"><span><small>وابسته به زمان</small>{html.escape(values[0])}</span><i></i><span><small>مقیاس‌پذیر</small>{html.escape(values[1])}</span></div>'
    else:
        body = '<div class="concept"><div><i></i><small>×۱</small></div><div><i></i><i></i><i></i><i></i><small>×۴</small></div><div class="many"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><small>×۱۶</small></div></div>'
    return (
        f'<section id="{beat.id}" data-motion="{html.escape(beat.motion_style)}" class="visual-beat {beat.visual_type} {beat.accent} {beat.layout} clip" '
        f'data-start="{beat.start:.3f}" data-duration="{beat.end - beat.start:.3f}" data-track-index="2">'
        f'<div class="beat-inner"><div class="ghost">{html.escape(beat.anchor_word)}</div><div class="eyebrow">{html.escape(beat.narrative_role)}</div><h2 dir="rtl">{title}</h2>{body}</div></section>'
    )


def _timeline_script(beats: list[VisualBeat]) -> str:
    lines = ['const tl = gsap.timeline({ paused: true });']
    for beat in beats:
        duration = beat.end - beat.start
        selector = f"#{beat.id} .beat-inner"
        entrances = {
            "slam": ('{opacity:0,scale:1.34,rotation:2}', '"back.out(1.45)"'),
            "wipe": ('{opacity:0,x:520,clipPath:"inset(0 0 0 100%)"}', '"power4.out"'),
            "assemble": ('{opacity:0,y:180,rotation:-3}', '"expo.out"'),
            "orbit": ('{opacity:0,scale:.55,rotation:-14}', '"power3.out"'),
            "type_on": ('{opacity:0,filter:"blur(24px)"}', '"power2.out"'),
            "count_up": ('{opacity:0,y:-120,scale:.8}', '"back.out(1.7)"'),
            "collage": ('{opacity:0,x:-260,rotation:5}', '"power3.out"'),
        }
        origin, ease = entrances.get(beat.motion_style, ('{opacity:0,y:90,scale:.94}', '"power3.out"'))
        lines.append(f'tl.fromTo("{selector}", {origin}, {{opacity:1,x:0,y:0,scale:1,rotation:0,clipPath:"inset(0 0 0 0)",filter:"blur(0px)",duration:.52,ease:{ease},immediateRender:false}}, {beat.start:.3f});')
        lines.append(
            f'tl.to("{selector}", {{opacity:0,duration:.22,ease:"power1.in"}}, '
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
            child = ".ui-stage i" if beat.visual_type == "ui_showcase" else ".collage div"
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
    (project_dir / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "media": {"autoProxy": True},
    }, indent=2))
    from .registry_runtime import wire_registry
    wire_registry(project_dir, beats)
    visual_library = []
    for beat in beats:
        value = beat.model_dump()
        visual_library.append(value)
    metadata = {
        "id": "ai-render-talking-2", "name": "AI Render Talking 2",
        "visual_library": visual_library,
    }
    (project_dir / "meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
    cards = "\n".join(_beat_markup(beat) for beat in beats)
    document = f'''<!doctype html>
<html lang="fa"><head><meta charset="UTF-8"><meta name="viewport" content="width=1080,height=1920">
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>
@font-face{{font-family:Ray;src:url('./assets/ray-extrabold.ttf')}}
*{{box-sizing:border-box}}html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;background:#080b0c}}
#root{{position:relative;width:100%;height:100%;overflow:hidden;font-family:Ray,sans-serif}}
.base{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}}
.visual-beat{{--bg:#f3f0e8;--fg:#151a1b;position:absolute;left:42px;right:42px;top:72px;height:720px;padding:62px 58px;border-radius:42px;overflow:hidden;background:var(--bg);color:var(--fg);box-shadow:0 28px 80px #0007;direction:rtl}}
.visual-beat.full_frame{{inset:0;height:1920px;border-radius:0;display:grid;align-items:center}}
.visual-beat.full_frame .beat-inner{{padding:240px 86px}}.visual-beat.full_frame h2{{font-size:108px;max-width:920px}}
.beat-inner{{position:absolute;inset:0;padding:62px 58px;opacity:0}}
.visual-beat:after{{content:"";position:absolute;inset:0;border:2px solid color-mix(in srgb,var(--fg) 12%,transparent);border-radius:42px;pointer-events:none}}
.ghost{{position:absolute;left:-20px;top:8px;font-size:190px;opacity:.045;white-space:nowrap;direction:rtl}}.eyebrow{{font-size:22px;color:color-mix(in srgb,var(--fg) 55%,transparent);margin-bottom:25px;letter-spacing:.08em}}h2{{font-size:66px;line-height:1.28;margin:0;max-width:870px;letter-spacing:-.02em}}
.teal{{--accent:#19a58f;--bg:#eaf5ef;--fg:#102b27}}.amber{{--accent:#ffb000;--bg:#fff4ce;--fg:#32240b}}.coral{{--accent:#ff6047;--bg:#2a1110;--fg:#fff2e8}}.blue{{--accent:#72a7ff;--bg:#0c2340;--fg:#edf5ff}}.ink{{--accent:#d4ff42;--bg:#131619;--fg:#f4f5ef}}.stat{{font-size:150px;color:var(--accent);margin-top:58px;line-height:1}}
.meter{{height:18px;background:#d8d4ca;border-radius:12px;margin-top:34px;overflow:hidden;direction:ltr}}.meter i{{display:block;width:78%;height:100%;background:var(--accent);transform-origin:left}}
.step{{display:flex;align-items:center;gap:24px;margin-top:27px;font-size:40px}}.step b{{display:grid;place-items:center;width:72px;height:72px;border-radius:22px;background:var(--accent);color:white;font-size:28px}}.step span{{border-bottom:2px solid #151a1b20;padding:10px 0;flex:1}}
.compare{{display:grid;grid-template-columns:1fr 120px 1fr;align-items:center;gap:18px;margin-top:70px;text-align:center}}.compare>div{{height:220px;border:3px solid currentColor;border-radius:34px;display:grid;place-items:center;padding:20px}}.compare strong{{display:block;font:900 80px/1 Ray;color:var(--accent)}}.compare span{{font-size:31px}}.compare i{{font-style:normal;color:var(--accent);font-size:74px}}.compare i b{{font-weight:900}}
.concept{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:30px;align-items:end;height:300px;margin-top:38px;direction:ltr}}.concept>div{{display:flex;flex-wrap:wrap;align-content:flex-end;justify-content:center;gap:10px;padding:24px;border-bottom:5px solid var(--accent);min-height:130px}}.concept>div:nth-child(2){{min-height:205px}}.concept>div:nth-child(3){{min-height:280px}}.concept i{{display:block;width:45px;height:45px;border-radius:12px;background:var(--accent)}}.concept small{{width:100%;font:900 32px Ray;color:var(--fg);text-align:center}}
.ui-stage{{position:relative;height:360px;margin-top:28px;perspective:900px}}.ui-stage i{{position:absolute;width:250px;height:300px;border-radius:26px;background:#171c1d;border:4px solid #fff;box-shadow:0 24px 45px #0005}}.ui-stage i:nth-child(1){{right:70px;transform:rotate(7deg)}}.ui-stage i:nth-child(2){{right:320px;top:22px;transform:scale(1.08)}}.ui-stage i:nth-child(3){{right:570px;transform:rotate(-7deg)}}.ui-stage span{{position:absolute;right:365px;top:75px;width:160px;height:16px;background:var(--accent);box-shadow:0 45px #ffffff30,0 90px #ffffff30}}
.collage{{display:grid;grid-template-columns:1fr 1fr;gap:18px;height:350px;margin-top:28px;direction:rtl}}.collage div{{display:grid;grid-template-columns:74px 1fr;align-items:center;gap:15px;padding:18px 22px;border-radius:24px;background:color-mix(in srgb,var(--fg) 8%,transparent);border:2px solid color-mix(in srgb,var(--fg) 22%,transparent)}}.collage b{{display:grid;place-items:center;width:64px;height:64px;border-radius:18px;background:var(--accent);color:var(--bg);font-size:34px}}.collage span{{font-size:30px}}
.chat-stack{{display:flex;flex-direction:column;gap:18px;margin-top:40px}}.bubble{{max-width:72%;padding:20px 28px;border-radius:28px;font-size:34px}}.bubble.b0{{align-self:flex-start;background:#e1ddd3}}.bubble.b1{{align-self:flex-end;background:var(--accent);color:#fff}}
.route{{height:300px;margin-top:25px}}.route svg{{width:100%;height:100%;overflow:visible}}.route path{{fill:none;stroke:var(--accent);stroke-width:14;stroke-linecap:round;stroke-dasharray:22 22}}.route circle{{fill:#f3f0e8;stroke:var(--accent);stroke-width:12}}
.saas-mark{{display:grid;grid-template-columns:190px 80px 1fr;align-items:center;gap:20px;margin-top:46px;direction:ltr}}.saas-mark>b{{display:grid;place-items:center;width:180px;height:180px;border-radius:48px;background:var(--accent);color:var(--bg);font:900 110px Ray}}.saas-mark>i{{height:5px;background:var(--accent);position:relative}}.saas-mark>i:after{{content:"";position:absolute;right:-2px;top:-11px;border:13px solid transparent;border-left-color:var(--accent)}}.saas-mark>div{{display:flex;flex-direction:column;gap:9px}}.saas-mark span{{font:900 35px/1.2 Ray;color:var(--fg)}}
.kinetic{{font-size:118px;line-height:1.3;margin-top:55px;color:var(--accent);max-width:900px;min-height:190px;padding-bottom:30px;overflow:hidden}}
.kinetic_type h2{{display:none}}.kinetic_type .kinetic{{font-size:132px;margin-top:160px;max-width:920px}}
.before-after{{display:grid;grid-template-columns:1fr 90px 1fr;gap:18px;align-items:center;margin-top:65px;font-size:34px;text-align:center}}.before-after span{{height:210px;border-radius:32px;border:3px solid currentColor;display:flex;flex-direction:column;justify-content:center;padding:24px}}.before-after small{{display:block;color:var(--accent);font-size:23px;margin-bottom:15px}}.before-after i{{height:5px;background:var(--accent);position:relative}}.before-after i:after{{content:"→";position:absolute;left:28px;top:-38px;color:var(--accent);font-style:normal;font-size:60px}}
.registry-stage{{position:relative;width:100%;height:360px;margin-top:26px;overflow:hidden;border-radius:28px;background:#fffdf8}}.registry-stage>[data-composition-src]{{position:absolute;inset:0;width:100%;height:100%}}
</style></head><body><main id="root" data-composition-id="main" data-start="0" data-duration="{duration:.3f}" data-width="1080" data-height="1920">
<video id="rough-cut" class="base clip" src="./assets/base.mp4" data-start="0" data-duration="{duration:.3f}" data-track-index="0" data-has-audio="true"></video>
{cards}</main><script>{_timeline_script(beats)}</script></body></html>'''
    entry = project_dir / "index.html"
    entry.write_text(document)
    return entry

"""The panel library: curated HyperFrames registry components (Apache-2.0, vendored in assets/hyperframes_components) and how a beat fills them.

Every entry was rendered with Persian text and the pack's design tokens and kept only if the text joins and reads correctly. A component is a
finished piece of professional motion, so variety comes from the library and from never using one twice in a reel, not from templates written
here. `choose()` is deterministic (same beat, same pick) and takes the components already used so the reel never repeats a motion.
"""
from __future__ import annotations

import hashlib
import json
import math
from html.parser import HTMLParser
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

LIBRARY_DIR = Path(__file__).resolve().parents[1] / "assets" / "hyperframes_components"

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٫٬", "0123456789.,")


def number_of(text: str) -> tuple[float, str, str] | None:
    """(value, prefix, suffix) of the first number in a title: '۳۰٪ بیشتر' -> (30, '', '%')."""
    m = re.search(r"([^\d۰-۹\s]{0,2})\s*([0-9۰-۹][0-9۰-۹,٬.٫]*)\s*(٪|%|k|K|M|x|X|ی|برابر)?", text or "")
    if not m:
        return None
    try:
        value = float(m.group(2).translate(_DIGITS).replace(",", ""))
    except ValueError:
        return None
    suffix = {"٪": "%", "%": "%", "k": "k", "K": "k", "M": "M", "x": "x", "X": "x", "برابر": "x"}.get(m.group(3) or "", "")
    return value, "", suffix


@dataclass(frozen=True)
class Entry:
    name: str
    roles: tuple[str, ...]            # list | compare | stat | headline | concept | cta | steps
    fill: Callable[[dict, float], dict]
    min_items: int = 0
    max_items: int = 9
    note: str = ""
    zoom: float = 1.8                  # the component is laid out in a container 1/zoom as wide, then scaled up: bigger type on a phone


def _items(beat: dict, low: int = 1, high: int = 6) -> list[str]:
    values = [str(i).strip() for i in (beat.get("items") or []) if str(i).strip()]
    return values[:high] if len(values) >= low else values


def _csv(values: list[str]) -> str:
    return ",".join(v.replace(",", "،") for v in values)


def _head_tail(title: str) -> tuple[str, str]:
    words = title.split()
    if len(words) <= 1:
        return "", title
    return " ".join(words[:-1]), words[-1]


def _fill_timeline(b, d):
    items = _items(b, 2, 4)
    return {"labels": _csv(items), "beatCount": len(items), "interval": round(max(0.45, min(1.1, d * 0.75 / max(1, len(items)))), 2)}


def _fill_stat_ring(b, d):
    n = number_of(b.get("title", "")) or (72.0, "", "%")
    return {"progress": min(100, n[0]) if n[0] <= 100 else 100, "label": f"{int(n[0]) if n[0] == int(n[0]) else n[0]}{n[2]}"}


def _fill_count_up(b, d):
    n = number_of(b.get("title", "")) or (100.0, "", "%")
    return {"start": 0, "end": n[0], "prefix": n[1], "suffix": n[2] or ""}


def _fill_chart(b, d):
    items = _items(b, 2, 4)
    n = len(items) if len(items) >= 2 else 4
    values = [round(18 + 82 * (k + 1) / n) for k in range(n)]
    return {"type": "bars", "data": ", ".join(str(v) for v in values), "labels": ", ".join(items if len(items) >= 2 else ["۱", "۲", "۳", "۴"]), "emphasize": n, "unit": "%"}


def _fill_hub(b, d):
    items = _items(b, 2, 5)
    return {"hub_label": (b.get("title") or "")[:18] or items[0], "nodes": _csv(items[:5] if len(items) >= 2 else items)}


def _fill_radial(b, d):
    items = _items(b, 2, 6)
    return {"center_label": (b.get("title") or "")[:18], "chips": _csv(items)}


def _fill_compare(a, b2):
    def fill(b, d):
        items = _items(b, 2, 2)
        left, right = (items + ["", ""])[:2]
        return {a: left, b2: right}
    return fill


def _fill_split_tilt(b, d):
    items = _items(b, 2, 2)
    left, right = (items + ["", ""])[:2]
    return {"label_a": left, "label_b": right, "badge_a": "۱", "badge_b": "۲"}


def _fill_text(key):
    return lambda b, d: {key: (b.get("title") or "").strip()}


def _fill_marker(b, d):
    head, tail = _head_tail((b.get("title") or "").strip())
    return {"text": (b.get("title") or "").strip(), "emphasis_word": tail}


def _fill_vox(b, d):
    head, tail = _head_tail((b.get("title") or "").strip())
    items = _items(b, 1, 1)
    return {"text": (b.get("title") or "").strip(), "keyword": tail, "note": items[0] if items else ""}


def _fill_headline_slam(b, d):
    title = (b.get("title") or "").strip()
    words = title.split()
    return {"text": title, "accent_word_index": max(0, len(words) - 1)}


def _fill_titlecard(b, d):
    items = _items(b, 1, 1)
    return {"headline": (b.get("title") or "").strip(), "kicker": items[0] if items else ""}


def _fill_line_swap(b, d):
    items = _items(b, 2, 2)
    head, tail = _head_tail(items[1] if len(items) > 1 else (b.get("title") or ""))
    return {"line_a": items[0] if items else (b.get("title") or ""), "line_b": items[1] if len(items) > 1 else (b.get("title") or ""),
            "underline_word": tail, "swap_at": round(max(1.0, min(2.2, d * 0.4)), 2)}


def _fill_swap(b, d):
    items = _items(b, 2, 4)
    return {"prefix": (b.get("title") or "")[:24], "options": _csv(items)}


def _fill_cta(b, d):
    items = _items(b, 1, 2)
    return {"action_line": (b.get("title") or "").strip(), "button_label": items[0] if items else "ادامه", "microcopy": items[1] if len(items) > 1 else ""}


def _fill_notes(b, d):
    items = _items(b, 1, 3)
    return {"title": (b.get("title") or "").strip().replace(" | ", "|"), "lines": "|".join(items)}


def _fill_notifications(b, d):
    items = _items(b, 2, 4)
    return {"titles": _csv(items), "bodies": _csv([(b.get("title") or "")[:40]] * len(items))}


def _fill_pull_back(b, d):
    n = number_of(b.get("title", ""))
    items = _items(b, 1, 1)
    return {"detail_text": (f"{int(n[0]) if n[0] == int(n[0]) else n[0]}{n[2]}" if n else (items[0] if items else "★")), "headline": (b.get("title") or "").strip()}


def _fill_marquee(b, d):
    items = _items(b, 2, 6)
    return {"words": ", ".join(items)}


def _fill_words(b, d):
    return {"words": _csv(_items(b, 1, 6) or [(b.get("title") or "")])}


def _fill_social(b, d):
    items = _items(b, 3, 3) + ["", "", ""]
    return {"brand": (b.get("title") or "")[:22], "proof": items[0], "cta": items[1], "f1": f"{items[0]}", "f2": f"{items[1]}", "f3": f"{items[2]}"}


LIBRARY: dict[str, Entry] = {e.name: e for e in (
    # lists / steps
    Entry("beat-timeline", ("list", "steps"), _fill_timeline, 2, 4, zoom=1.8),
    Entry("grid-card-assemble", ("list",), lambda b, d: {"items": _csv(_items(b, 2, 6))}, 2, 6, zoom=1.6),
    Entry("state-chip-rail", ("list", "steps"), lambda b, d: {"states": _csv(_items(b, 2, 5))}, 2, 5, zoom=2.8),
    Entry("pan-stations", ("list", "steps"), lambda b, d: {"labels": _csv(_items(b, 2, 4)), "stationCount": len(_items(b, 2, 4))}, 2, 4, zoom=1.4),
    Entry("tracing-beam", ("steps",), lambda b, d: {"labels": _csv(_items(b, 2, 3))}, 2, 3, zoom=1.8),
    Entry("notification-stack", ("list",), _fill_notifications, 2, 4, zoom=1.5),
    Entry("kinetic-type-swap", ("list", "headline"), _fill_swap, 2, 4, zoom=2.4),
    Entry("perspective-marquee", ("list",), _fill_marquee, 2, 6, zoom=1.5),
    Entry("multiplayer-cursors", ("list", "concept"), lambda b, d: {"labels": _csv(_items(b, 2, 4)), "cursorCount": len(_items(b, 2, 4))}, 2, 4, zoom=2.2),
    # compare
    Entry("split-tilt-cards", ("compare",), _fill_split_tilt, 2, 2, zoom=1.3),
    Entry("comparison-split", ("compare",), _fill_compare("labelA", "labelB"), 2, 2, zoom=1.0),
    Entry("before-after-wipe", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.0),
    Entry("focus-rack", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.3),
    Entry("match-cut", ("compare",), _fill_compare("label_a", "label_b"), 2, 2, zoom=1.0),
    # numbers
    Entry("conic-progress-ring", ("stat",), _fill_stat_ring, zoom=1.5),
    Entry("count-up", ("stat",), _fill_count_up, zoom=2.4),
    Entry("chart-story", ("stat", "list"), _fill_chart, 0, 4, zoom=1.2),
    Entry("pull-back-reveal", ("stat", "headline"), _fill_pull_back, zoom=1.4),
    Entry("star-rating-fill", ("stat",), lambda b, d: {"rating": 4.8}, zoom=1.8),
    # headlines / emphasis
    Entry("headline-slam", ("headline",), _fill_headline_slam, zoom=2.4),
    Entry("marker-highlight", ("headline",), _fill_marker, zoom=2.4),
    Entry("push-in", ("headline",), _fill_text("text"), zoom=1.6),
    Entry("text-shimmer", ("headline",), _fill_text("text"), zoom=2.2),
    Entry("titlecard-calm", ("headline",), _fill_titlecard, zoom=1.8),
    Entry("vox-annotate", ("headline",), _fill_vox, zoom=2.2),
    Entry("line-swap", ("headline", "compare"), _fill_line_swap, 0, 2, zoom=2.2),
    Entry("per-word-rise", ("headline",), _fill_text("text"), zoom=2.4),
    Entry("svg-mask-reveal", ("headline",), _fill_text("text"), zoom=1.6),
    Entry("drift-hold", ("headline",), _fill_text("text"), zoom=2.2),
    Entry("typed-prompt", ("headline",), _fill_text("text"), zoom=2.6),
    # concept maps
    Entry("constellation-hub", ("concept", "list"), _fill_hub, 2, 5, zoom=1.5),
    Entry("radial-surround", ("concept",), _fill_radial, 2, 6, zoom=1.6),
    Entry("overwhelm-surround", ("concept",), lambda b, d: {"centerLabel": (b.get("title") or "")[:16]}, zoom=1.2),
    Entry("avatar-cloud", ("concept",), lambda b, d: {"label": (b.get("title") or "")[:24]}, zoom=1.5),
    # closing / call to action
    Entry("cta-lockup", ("cta",), _fill_cta, zoom=1.8),
    Entry("cta-close", ("cta",), _fill_cta, zoom=2.2),
    Entry("notes-typing", ("steps", "list"), _fill_notes, 1, 3, zoom=1.3),
)}


def role_of(beat: dict) -> str:
    items = _items(beat, 1, 6)
    vtype = str(beat.get("visual_type") or "concept")
    title = str(beat.get("title") or "")
    if str(beat.get("role") or beat.get("narrative_role") or "") == "cta":
        return "cta"
    if vtype in {"comparison", "before_after"} and len(items) >= 2:
        return "compare"
    if vtype == "stat" or (not items and number_of(title)):
        return "stat"
    if vtype == "steps" and len(items) >= 2:
        return "steps"
    if len(items) >= 3:
        return "list"
    if len(items) == 2:
        return "concept" if vtype == "concept" else "compare"
    return "headline"


# Only reviewed, whole-word/textContent components are executable. Other vendored
# sources remain pinned and available for future maintained adapters.
SAFE_COMPONENTS = frozenset({
    "grid-card-assemble", "state-chip-rail", "tracing-beam", "notification-stack",
    "kinetic-type-swap", "split-tilt-cards", "comparison-split", "before-after-wipe",
    "focus-rack", "match-cut", "headline-slam", "push-in", "text-shimmer",
    "titlecard-calm", "per-word-rise", "svg-mask-reveal", "drift-hold",
    "constellation-hub", "radial-surround", "overwhelm-surround", "avatar-cloud",
    "cta-lockup",
})
LICENSE_SHA256 = "4259155fb06f127687ee7b0a8a3682d45132db0f2da26cbc0b7a2d1e796436b8"
# Reviewed content sinks only; everything else in a component is template chrome.
CONTENT_SELECTORS = {
    "grid-card-assemble": ".gca-label,.gca-body", "state-chip-rail": ".scr-chip,.scr-badge",
    "tracing-beam": ".tb-label", "notification-stack": ".ns-title,.ns-body",
    "kinetic-type-swap": ".kts-prefix,.kts-suffix,.kts-word",
    "split-tilt-cards": ".stc-label-a,.stc-label-b", "comparison-split": ".cs-label",
    "before-after-wipe": ".baw-chip-a,.baw-chip-b", "focus-rack": ".fr-label-a,.fr-label-b",
    "match-cut": ".mc-label-a,.mc-label-b", "headline-slam": ".hs-word",
    "push-in": ".pi-headline", "text-shimmer": ".ts-headline",
    "titlecard-calm": ".tc-headline,.tc-kicker", "per-word-rise": ".pwr-unit",
    "svg-mask-reveal": "#svg-mask-reveal-text,#svg-mask-reveal-outline", "drift-hold": ".dh-label",
    "constellation-hub": ".ch-hub,.ch-node", "radial-surround": ".rs-card-label,.rs-chip",
    "overwhelm-surround": ".os-center-label", "avatar-cloud": ".ac-label",
    "cta-lockup": ".cl-action,.cl-button,.cl-microcopy",
}

# Adapt job-local copies; the vendored sources and integrity pins stay immutable.
CHROME_COPY = {
    "Community": "جامعه", "Workspace": "فضای کار", "Match complete": "تطبیق انجام شد",
    "Step one": "گام نخست", "Step two": "گام دوم", "Step three": "گام سوم",
    "Inbox": "پیام‌ها", "99+": "۹۹+", "Due": "موعد", "@you": "برای شما",
    "ASAP": "فوری", "12": "۱۲", "Review": "بازبینی", "Call": "تماس",
    "3 pings": "۳ پیام", "Sync": "همگام", "Today": "امروز", "Reply": "پاسخ",
    "8 tabs": "۸ برگه", "Update": "به‌روزرسانی", "Now": "اکنون", "Draft": "پیش‌نویس",
    "4 alerts": "۴ هشدار", "Fix": "اصلاح", "Follow up": "پیگیری", "Queue": "صف",
    "2 min": "۲ دقیقه", "Waiting": "در انتظار", "+7": "+۷",
}


class PanelDataError(ValueError):
    pass


def clean_beat(beat: dict) -> dict:
    """Project stored/model data onto bounded fields; discard all legacy code."""
    from engine.persian_text import display_text
    def text(value, limit):
        return display_text(value[:limit]) if isinstance(value, str) else ""
    items = beat.get("items")
    return {"title": text(beat.get("title"), 160),
            "items": [text(i, 80) for i in items[:6] if isinstance(i, str)] if isinstance(items, list) else [],
            "visual_type": beat.get("visual_type") if isinstance(beat.get("visual_type"), str) and beat.get("visual_type") in
                {"kinetic_type", "concept", "comparison", "before_after", "stat", "steps"} else "concept",
            "role": "cta" if beat.get("role") == "cta" else "evidence",
            "component_id": beat.get("component_id") if isinstance(beat.get("component_id"), str) else ""}


def verified_source(name: str) -> str:
    """The manifest, license and exact local bytes are the execution boundary."""
    manifest = json.loads((LIBRARY_DIR / "MANIFEST.json").read_text())
    if name not in SAFE_COMPONENTS or name not in manifest["files"] or name not in LIBRARY:
        raise PanelDataError("Component is not in the reviewed manifest allowlist")
    if hashlib.sha256((LIBRARY_DIR / "LICENSE.hyperframes").read_bytes()).hexdigest() != LICENSE_SHA256:
        raise PanelDataError("Component license integrity mismatch")
    path = LIBRARY_DIR / f"{name}.html"
    if path.is_symlink() or not path.resolve().is_relative_to(LIBRARY_DIR.resolve()):
        raise PanelDataError("Component path escapes library")
    source = path.read_bytes()
    pin = manifest["files"][name]
    if len(source) != pin["bytes"] or hashlib.sha256(source).hexdigest() != pin["sha256"]:
        raise PanelDataError("Component integrity mismatch")
    return source.decode("utf-8")


class _Variables(HTMLParser):
    fields = None
    def handle_starttag(self, tag, attrs):
        if tag == "html":
            self.fields = json.loads(dict(attrs).get("data-composition-variables", "[]"))


def validate_values(name: str, values: dict) -> dict:
    parser = _Variables()
    parser.feed(verified_source(name))
    fields = {v["id"]: v for v in parser.fields or []}
    # Models fill content only. Style, timing, URLs, markup and arbitrary keys
    # never cross this boundary. Values are carried in escaped JSON attributes.
    allowed = set(LIBRARY[name].fill({"title": "سلام", "items": ["یک", "دو", "سه"]}, 4))
    if not isinstance(values, dict) or set(values) - allowed:
        raise PanelDataError("Unknown component content field")
    for key, value in values.items():
        field = fields.get(key)
        if not field or field.get("role") != "content":
            raise PanelDataError("Field is not component content")
        kind = field["type"]
        if kind == "string":
            if not isinstance(value, str) or len(value) > 1000:
                raise PanelDataError("Invalid component text")
        elif kind == "number":
            if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000:
                raise PanelDataError("Invalid component number")
        elif kind == "enum":
            if value not in [o["value"] if isinstance(o, dict) else o for o in field["options"]]:
                raise PanelDataError("Invalid component enum")
        elif kind == "boolean":
            if type(value) is not bool:
                raise PanelDataError("Invalid component boolean")
        else:
            raise PanelDataError("Unsupported component field type")
    return values


def install(project: Path, name: str) -> Path:
    """Adapt verified bytes only; never interpolate user data into source code."""
    source = verified_source(name)
    for english, persian in CHROME_COPY.items():
        source = source.replace('>' + english + '<', '>' + persian + '<')
        source = source.replace(json.dumps(english), json.dumps(persian, ensure_ascii=False))
    source = re.sub(r'>(0[123]|A|B)<', lambda m: '>' + {'01':'۰۱','02':'۰۲','03':'۰۳','A':'۱','B':'۲'}[m[1]] + '<', source)
    if name == "avatar-cloud":
        source = source.replace('avatar.textContent = lettermarks[index];', 'avatar.textContent = ["آ", "ب", "پ", "ت", "ث", "ج", "چ", "ح", "خ", "د"][index % 10];')
    source = source.replace('<div id="root"', '<div data-qc="chrome" id="root"')
    selectors = json.dumps(CONTENT_SELECTORS[name])
    source = source.replace('tl.seek(0);', f'root.querySelectorAll({selectors}).forEach(function(e){{e.dataset.qc="content";}});\n            tl.seek(0);')
    source = source.replace('lang="en"', 'lang="fa" dir="rtl"')
    source = re.sub(r'<script src="https://[^"<>]+"></script>',
                    '<script src="../../assets/gsap.min.js"></script>', source)
    source = re.sub(r'letter-spacing\s*:[^;}]+', 'letter-spacing:0', source)
    source = source.replace("</style>", """@font-face{font-family:Ray;src:url('../../assets/fonts/ray-extrabold.ttf')}
#root{direction:rtl;--font-display:Ray;--font-body:Ray} #root *{font-family:Ray!important;letter-spacing:0!important;text-transform:none!important}
</style>""", 1)
    target = project / "compositions" / "components" / f"{name}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source)
    receipts = project / "resource-receipts"
    receipts.mkdir(exist_ok=True)
    (receipts / "LICENSE.hyperframes").write_bytes((LIBRARY_DIR / "LICENSE.hyperframes").read_bytes())
    (receipts / f"{name}.json").write_text(json.dumps({
        "component": name, "upstream_commit": "3b2058a2b7a2", "license": "Apache-2.0",
        "source_sha256": hashlib.sha256(verified_source(name).encode()).hexdigest(),
        "adapter": "local-runtime-rtl-ray-v1", "adapted_sha256": hashlib.sha256(source.encode()).hexdigest(),
    }, indent=2))
    return target


def available() -> list[str]:
    ready = []
    for name in sorted(SAFE_COMPONENTS):
        try:
            verified_source(name)
            ready.append(name)
        except (OSError, ValueError):
            pass
    return ready


def choose(beat: dict, used: set[str], seed: str = "") -> tuple[str, dict] | None:
    """The component for this beat and the variable values that fill it; None when the library has nothing that fits."""
    beat = clean_beat(beat)
    role = role_of(beat)
    items = len(_items(beat, 1, 6))
    ready = set(available())

    def pool(r: str) -> list[str]:
        return sorted(n for n, e in LIBRARY.items() if n in ready and r in e.roles and e.min_items <= items <= e.max_items)

    requested = beat.get("component_id")
    if requested not in used and (requested in pool(role) or requested in pool("headline")):
        candidates = [requested]
    else:
        candidates = [n for n in pool(role) if n not in used] or [n for n in pool("headline") if n not in used] or [n for n in pool(role) if n not in used]
    if not candidates:
        return None
    pick = candidates[int(hashlib.sha1(f"{seed}{beat.get('title','')}".encode()).hexdigest(), 16) % len(candidates)]
    try:
        return pick, validate_values(pick, LIBRARY[pick].fill(beat, 4.0))
    except ValueError:
        return None

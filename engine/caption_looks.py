"""Where a caption sits on the frame, how big it is and what colour: the user's "look" for each caption.

A look is {"x", "y", "scale", "color"} (each optional): the caption's anchor in frame pixels, a size multiplier and a text
colour. It is applied to the ASS the style already built, so every style keeps drawing its own captions; nothing here
re-lays text out. Styles 2 and 3 draw one text line per caption; style 1 also draws a rounded box that must move and scale
with its text; style 4 draws captions with the Tscaps layer, which has its own per-cue hook (see ``tscaps_overlay``).

Events are matched to captions by time (an event ends when its caption ends and starts no earlier than the caption), the
same rule for reading geometry and for applying looks, so the timeline and the render cannot disagree.
"""
from __future__ import annotations

import re

W, H = 1080, 1920
LOOK_KEYS = ("x", "y", "scale", "color")
CAPTION_STYLES = {"caption", "key", "cap"}      # style 1 / style 2 / style 3 caption text styles
SCALE_RANGE = (0.4, 3.0)
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")



class _Event:
    """One ASS Dialogue line. Only the first nine commas separate fields; the text may contain more (``\\pos(x,y)``)."""

    def __init__(self, fields: list[str]):
        self.fields = fields

    def group(self, index: int) -> str:       # 1-based like re.Match, so call sites read the same as the ASS spec
        return self.fields[index - 1]

    def groups(self) -> tuple[str, ...]:
        return tuple(self.fields)


def _parse(line: str) -> "_Event | None":
    if not line.startswith("Dialogue: "):
        return None
    fields = line[len("Dialogue: "):].split(",", 9)
    return _Event(fields) if len(fields) == 10 else None

_POS = re.compile(r"\\pos\(\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)")
_FS = re.compile(r"\\fs(\d+(?:\.\d+)?)")


def clean_look(raw) -> dict:
    """Validated look fields only; raises ValueError on a bad value."""
    if not isinstance(raw, dict):
        return {}
    out = {}
    for key in ("x", "y", "scale"):
        if raw.get(key) is None:
            continue
        try:
            value = float(raw[key])
        except (TypeError, ValueError):
            raise ValueError(f"{key} must be a number")
        if value != value:
            raise ValueError(f"{key} must be a number")
        limits = {"x": (0, W), "y": (0, H), "scale": SCALE_RANGE}[key]
        if not limits[0] <= value <= limits[1]:
            raise ValueError(f"{key} is outside {limits[0]}..{limits[1]}")
        out[key] = round(value, 2)
    if raw.get("color") is not None:
        if not HEX.match(str(raw["color"])):
            raise ValueError("color must be #RRGGBB")
        out["color"] = str(raw["color"]).upper()
    return out


def _seconds(stamp: str) -> float:
    h, m, s = stamp.strip().split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def _bgr(color: str) -> str:
    return color[5:7] + color[3:5] + color[1:3]


def _style_fonts(lines: list[str]) -> dict[str, str]:
    fonts = {}
    for line in lines:
        if line.startswith("Style:"):
            fields = line[len("Style:"):].split(",")
            if len(fields) > 1:
                fonts[fields[0].strip()] = fields[1].strip()
    return fonts


def _style_sizes(lines: list[str]) -> dict[str, float]:
    sizes = {}
    for line in lines:
        if line.startswith("Style:"):
            fields = line[len("Style:"):].split(",")
            try:
                sizes[fields[0].strip()] = float(fields[2])
            except (IndexError, ValueError):
                pass
    return sizes


def _caption_for(captions: list[dict], start: float, end: float) -> int | None:
    for index, caption in enumerate(captions):
        if abs(end - float(caption["end"])) <= 0.03 and float(caption["start"]) - 0.03 <= start < float(caption["end"]):
            return index
    return None


def _path_size(path: str) -> tuple[float, float]:
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
    xs, ys = numbers[0::2], numbers[1::2]
    return (max(xs) - min(xs), max(ys) - min(ys)) if xs and ys else (0.0, 0.0)


def _groups(lines: list[str], captions: list[dict]):
    """(caption index) -> {"text": (line index, match), "box": (line index, match) | None}."""
    found: dict[int, dict] = {}
    boxes: dict[tuple[str, str], tuple[int, re.Match]] = {}
    for number, line in enumerate(lines):
        match = _parse(line)
        if not match:
            continue
        layer, start, end, style, *_rest, text = match.groups()
        if style == "plain" and r"\p1" in text and r"\an7" in text:
            boxes[(start, end)] = (number, match)
    for number, line in enumerate(lines):
        match = _parse(line)
        if not match:
            continue
        layer, start, end, style, *_rest, text = match.groups()
        if style not in CAPTION_STYLES:
            continue
        index = _caption_for(captions, _seconds(start), _seconds(end))
        if index is None or index in found:
            continue
        found[index] = {"text": (number, match), "box": boxes.get((start, end))}
    return found


def geometry(ass_text: str, captions: list[dict]) -> dict[int, dict]:
    """Where each caption sits in the ASS: {caption index: {"x","y","size","box": {"dx","dy","w","h"} | None, "style"}}."""
    lines = ass_text.splitlines()
    sizes, fonts = _style_sizes(lines), _style_fonts(lines)
    out = {}
    for index, parts in _groups(lines, captions).items():
        number, match = parts["text"]
        text = match.group(10)
        pos = _POS.search(text)
        if not pos:
            continue
        x, y = float(pos.group(1)), float(pos.group(2))
        fs = _FS.search(text)
        size = float(fs.group(1)) if fs else sizes.get(match.group(4), 0.0)
        box = None
        if parts["box"]:
            _n, box_match = parts["box"]
            box_pos = _POS.search(box_match.group(10))
            width, height = _path_size(box_match.group(10).split(r"\p1}", 1)[-1])
            if box_pos:
                box = {"dx": float(box_pos.group(1)) - x, "dy": float(box_pos.group(2)) - y, "w": width, "h": height}
        out[index] = {"x": x, "y": y, "size": size, "box": box, "style": match.group(4), "font": fonts.get(match.group(4), "")}
    return out


def _with(tags: str, adds: str) -> str:
    return tags + adds


def apply(ass_text: str, captions: list[dict]) -> str:
    """The ASS with each caption's look applied. Captions without a look, and every other event, are left untouched."""
    looks = {i: c["look"] for i, c in enumerate(captions) if c.get("look")}
    if not looks:
        return ass_text
    lines = ass_text.split("\n")
    sizes = _style_sizes(lines)
    for index, parts in _groups(lines, captions).items():
        look = looks.get(index)
        if not look:
            continue
        number, match = parts["text"]
        text = match.group(10)
        pos = _POS.search(text)
        if not pos or not text.startswith("{"):
            continue
        tx, ty = float(pos.group(1)), float(pos.group(2))
        nx, ny = look.get("x", tx), look.get("y", ty)
        scale = float(look.get("scale", 1.0))
        tags_end = text.index("}")
        tags, rest = text[1:tags_end], text[tags_end + 1:]
        tags = _POS.sub(lambda _m: f"\\pos({nx:.1f},{ny:.1f})", tags, count=1)
        if scale != 1.0:
            fs = _FS.search(tags)
            base = float(fs.group(1)) if fs else sizes.get(match.group(4), 0.0)
            if base:
                new = f"\\fs{round(base * scale)}"
                # a lambda: in a plain replacement string "\\f" would be read as a form feed
                tags = _FS.sub(lambda _m: new, tags, count=1) if fs else tags.replace("\\q2", "\\q2" + new, 1) if "\\q2" in tags else tags + new
        if look.get("color"):
            tags = tags.replace("\\q2", f"\\q2\\1c&H{_bgr(look['color'])}&", 1) if "\\q2" in tags else tags + f"\\1c&H{_bgr(look['color'])}&"
        fields = list(match.groups())
        fields[9] = "{" + tags + "}" + rest
        lines[number] = "Dialogue: " + ",".join(fields)
        if parts["box"]:
            box_number, box_match = parts["box"]
            box_text = box_match.group(10)
            box_pos = _POS.search(box_text)
            if box_pos:
                bx = nx + scale * (float(box_pos.group(1)) - tx)
                by = ny + scale * (float(box_pos.group(2)) - ty)
                moved = _POS.sub(lambda _m: f"\\pos({bx:.1f},{by:.1f})", box_text, count=1)
                if scale != 1.0:
                    moved = moved.replace("\\p1", f"\\fscx{round(100 * scale)}\\fscy{round(100 * scale)}\\p1", 1)
                box_fields = list(box_match.groups())
                box_fields[9] = moved
                lines[box_number] = "Dialogue: " + ",".join(box_fields)
    return "\n".join(lines)


def effective_rect(frame: dict, look: dict | None, text_width: float = 0.0) -> dict:
    """The caption's rectangle on the frame after its look: {"x","y","w","h"} (top-left corner and size, frame px)."""
    look = look or {}
    scale = float(look.get("scale", 1.0))
    ax, ay = look.get("x", frame["x"]), look.get("y", frame["y"])
    if frame.get("box"):
        box = frame["box"]
        return {"x": ax + scale * box["dx"], "y": ay + scale * box["dy"], "w": box["w"] * scale, "h": box["h"] * scale}
    w = (text_width or frame["size"] * 6) * scale
    h = frame["size"] * 1.35 * scale
    return {"x": ax - w / 2, "y": ay - h / 2, "w": w, "h": h}

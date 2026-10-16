"""Media side of Persian video localization (see ``brain.localize``).

* find where the burned-in English title and captions sit (tesseract OCR,
  matched against the words spoken at that moment so on-screen UI text in
  the footage is ignored)
* place Persian voice clips on the English timeline
* write an ASS file whose Persian boxes cover the English captions
* render picture, captions, emoji, optional logo and the new audio mix in a
  single ffmpeg pass (requires an ffmpeg with libass, see ``render_ass``)
"""
from __future__ import annotations

import csv
import difflib
import io
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from .render_ass import ass_burner_ffmpeg, subtitles_filter

log = logging.getLogger(__name__)

# Box colour name -> (box, text) colours. Unless the project picks one,
# every render takes the next colour (see ``app.localize``).
BOX_STYLES = {
    "black": ("#000000", "#FFFFFF"),
    "white": ("#FFFFFF", "#000000"),
    "red": ("#C62828", "#FFFFFF"),
    "blue": ("#1565C0", "#FFFFFF"),
    "green": ("#2E7D32", "#FFFFFF"),
}
PAD_X, PAD_Y = 0.25, 0.09       # box padding, as a fraction of the font size
LINE_PITCH = 1.05               # line spacing of two-line captions, x font size
MAX_TEXT_FRACTION = 0.88        # widest text, as a fraction of the frame width
# End card shown after the source ends (instead of a frozen last frame).
END_CARD_SECONDS = 3.5
END_CARD_BG, END_CARD_GRID = "#141414", "#262626"
END_CARD_BOX, END_CARD_HIGHLIGHT = "#2A2A2A", "#F2C230"
END_CARD_LINES = ("عدد {n} رو کامنت کن تا قدم به قدم و رایگان", "یادت بدم بیزینس آنلاین خودت رو بسازی")
END_CARD_FONT = "Ray ExtraBlack"
TEXT_COLOUR = "#FFFFFF"
DEFAULT_TITLE_Y = 0.09          # fraction of frame height
DEFAULT_CAPTION_Y = 0.56
MAX_TEMPO = 1.35                # fastest speed-up applied to fit a voice clip
MUSIC_VOLUME_DB = -20.0
EMOJI_FONT = Path("/System/Library/Fonts/Apple Color Emoji.ttc")


# --- geometry ---------------------------------------------------------------

def output_size(src_w: int, src_h: int) -> tuple[int, int]:
    """Portrait sources render at 1080 wide; keep the aspect, even dimensions."""
    if src_w >= 1080:
        return src_w & ~1, src_h & ~1
    scale = 1080 / src_w
    return 1080, int(round(src_h * scale)) & ~1


def probe_fps(path: Path) -> str:
    """Frame rate as an ffmpeg rational (e.g. "30000/1001"); 30 when unknown."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True,
    ).stdout.strip()
    return out if re.fullmatch(r"\d+(/\d+)?", out or "") and not out.startswith("0") else "30"


def probe_video(path: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height:format=duration", "-of", "csv=p=0:s=,", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    w, h = (int(v) for v in out[0].split(",")[:2])
    return w, h, float(out[-1].split(",")[0])


# --- OCR --------------------------------------------------------------------

def _norm(token: str) -> str:
    return re.sub(r"[^a-z0-9]", "", token.lower())


def _tesseract_tsv(image: Path) -> list[dict]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return []
    proc = subprocess.run([tesseract, str(image), "-", "--psm", "11", "tsv"],
                          capture_output=True, text=True)
    tokens = []
    for row in csv.DictReader(io.StringIO(proc.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        text = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            continue
        if conf < 55 or len(_norm(text)) < 2:
            continue
        tokens.append({
            "text": text, "x": int(row["left"]), "y": int(row["top"]),
            "w": int(row["width"]), "h": int(row["height"]),
        })
    return tokens


def _caption_mask(frame: Path, out: Path) -> Optional[Path]:
    """Black-on-white image of bright or saturated pixels outlined in black.

    Social captions are white, yellow or green with a dark outline; tesseract
    reads the white ones on the raw frame but misses coloured ones.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    img = cv2.imread(str(frame))
    if img is None:
        return None
    _, sat, val = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
    glyph = ((val > 170) & (sat > 110)) | ((val > 215) & (sat < 45))
    near_outline = cv2.dilate((val < 70).astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    mask = cv2.morphologyEx((glyph & near_outline).astype(np.uint8) * 255,
                            cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    cv2.imwrite(str(out), 255 - mask)
    return out


def _outlined_text(frame: Path) -> list[dict]:
    """Boxes of burned-in caption text, found by its thick dark outline.

    Coloured captions on a bright background (yellow on a white web page)
    defeat tesseract, but every glyph is a bright or saturated shape ringed
    by a thick black outline. Such glyphs of caption height lined up in a
    row are caption text; thin dark UI text has no thick outline.
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []
    img = cv2.imread(str(frame))
    if img is None:
        return []
    H, W = img.shape[:2]
    _, sat, val = cv2.split(cv2.cvtColor(img, cv2.COLOR_BGR2HSV))
    thick_dark = cv2.erode((val < 60).astype(np.uint8), np.ones((3, 3), np.uint8))
    near = cv2.dilate(thick_dark, np.ones((7, 7), np.uint8)) > 0
    glyph = ((val > 170) & (sat > 110)) | ((val > 215) & (sat < 45))
    _, _, stats, _ = cv2.connectedComponentsWithStats((glyph & near).astype(np.uint8), 8)
    letters = sorted((tuple(int(v) for v in s[:4]) for s in stats[1:]
                      if 0.018 * H <= s[3] <= 0.07 * H and s[2] <= 0.12 * W and s[4] >= 0.045 * s[2] * s[3]),
                     key=lambda s: s[0])
    rows: list[list[tuple[int, int, int, int]]] = []
    for x, y, w, h in letters:
        for row in rows:
            row_h = _median([r[3] for r in row])
            row_cy = _median([r[1] + r[3] / 2 for r in row])
            right = max(r[0] + r[2] for r in row)
            if abs(y + h / 2 - row_cy) < 0.35 * row_h and 0.6 < h / row_h < 1.6 and x - right < 0.9 * row_h:
                row.append((x, y, w, h))
                break
        else:
            rows.append([(x, y, w, h)])
    boxes = []
    for row in rows:
        tall = _median([r[3] for r in row]) >= 0.025 * H
        if len(row) >= 3 or (len(row) == 2 and tall):
            box = _union([{"x": x, "y": y, "w": w, "h": h} for x, y, w, h in row])
            boxes.append({**box, "text": "", "outlined": True})
    return boxes


def _ocr_tokens(frame: Path) -> list[dict]:
    """Tokens from the raw frame plus the caption-colour mask, de-duplicated."""
    tokens = _tesseract_tsv(frame)
    masked = _caption_mask(frame, frame.with_name(frame.stem + "_mask.png"))
    if masked:
        for tok in _tesseract_tsv(masked):
            # Text that survives the mask is outlined caption-style text
            # (burned overlay), not text on a screen in the footage.
            same = next((t for t in tokens if abs(tok["x"] - t["x"]) < t["h"] and abs(tok["y"] - t["y"]) < t["h"]), None)
            if same:
                same["styled"] = True
            else:
                tokens.append({**tok, "styled": True})
    return tokens + _outlined_text(frame)


def _grab(video: Path, t: float, out: Path) -> bool:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0.0, t):.3f}", "-i", str(video),
                    "-frames:v", "1", str(out)], capture_output=True)
    return out.is_file()


def _is_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


def _union(boxes: list[dict]) -> Optional[dict]:
    if not boxes:
        return None
    x0 = min(b["x"] for b in boxes)
    y0 = min(b["y"] for b in boxes)
    x1 = max(b["x"] + b["w"] for b in boxes)
    y1 = max(b["y"] + b["h"] for b in boxes)
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


def _matches(token: str, vocabulary: set[str]) -> bool:
    t = _norm(token)
    if t in vocabulary:
        return True
    return any(len(v) >= 3 and difflib.SequenceMatcher(None, t, v).ratio() >= 0.8 for v in vocabulary)


def _normalized(box: Optional[dict], w: int, h: int) -> Optional[dict]:
    if not box:
        return None
    return {"cx": (box["x"] + box["w"] / 2) / w, "cy": (box["y"] + box["h"] / 2) / h,
            "w": box["w"] / w, "h": box["h"] / h}


SAMPLE_FPS = 4                  # OCR frames per second of video
_MAX_CAPTION_H = 0.14           # caption boxes taller than this are OCR noise


def _caption_hits(tokens: list[dict], vocab: set[str], min_h: float, w: int, h: int) -> list[dict]:
    """OCR tokens that belong to the spoken caption, plus their row neighbours."""
    big = [t for t in tokens if t["h"] >= min_h]
    # Burned social captions are large ALL-CAPS words; screen text in the
    # footage is small or mixed case. Count either a spoken-word match or a
    # large all-caps token (the caption may not use the transcript's words).
    hits = [t for t in big if _matches(t["text"], vocab)
            or (t["h"] >= min_h * 1.1 and _is_caps(t["text"]))]
    for hit in list(hits):
        # Short tokens on the same caption row ("TO", numbers) that the
        # transcript spells differently.
        hits += [t for t in big if t not in hits
                 and abs(t["y"] - hit["y"]) < hit["h"] * 0.5
                 and 0.6 < t["h"] / hit["h"] < 1.6
                 and abs(t["x"] - hit["x"]) < w * 0.45]
    if not hits:
        return []
    # Keep the densest band of rows: matches scattered over the frame come
    # from on-screen UI text that happens to share a word with the caption.
    anchor = max(hits, key=lambda t: sum(abs(o["y"] - t["y"]) < _MAX_CAPTION_H * h / 2 for o in hits))
    return [t for t in hits if abs(t["y"] - anchor["y"]) < _MAX_CAPTION_H * h / 2]


def _median(values: list[float]) -> float:
    values = sorted(values)
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def _extract_frames(video: Path, out_dir: Path, fps: int) -> list[tuple[float, Path]]:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={fps}",
                    str(out_dir / "f_%05d.png")], capture_output=True, check=True)
    frames = sorted(out_dir.glob("f_*.png"))
    # The fps filter emits frame k at (k + 0.5) / fps on average.
    return [((k + 0.5) / fps, path) for k, path in enumerate(frames)]


def _merge_windows(windows: list[dict]) -> list[dict]:
    """Merge consecutive cover windows whose boxes overlap closely."""
    merged: list[dict] = []
    for item in windows:
        prev = merged[-1] if merged else None
        if (prev and item["start"] - prev["end"] < 0.3
                and abs(prev["box"]["cy"] - item["box"]["cy"]) < 0.02
                and abs(prev["box"]["cx"] - item["box"]["cx"]) < 0.05
                and prev.get("caps") == item.get("caps")):
            prev["end"] = item["end"]
            pb, ib = prev["box"], item["box"]
            x0 = min(pb["cx"] - pb["w"] / 2, ib["cx"] - ib["w"] / 2)
            x1 = max(pb["cx"] + pb["w"] / 2, ib["cx"] + ib["w"] / 2)
            y0 = min(pb["cy"] - pb["h"] / 2, ib["cy"] - ib["h"] / 2)
            y1 = max(pb["cy"] + pb["h"] / 2, ib["cy"] + ib["h"] / 2)
            prev["box"] = {"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "w": x1 - x0, "h": y1 - y0}
            prev["caps"] = prev.get("caps", False) or item.get("caps", False)
            prev["words"] = sorted(set(prev.get("words", [])) | set(item.get("words", [])))
        else:
            merged.append({**item, "box": dict(item["box"])})
    return merged


def ocr_video(video: Path) -> dict:
    """OCR tokens of frames sampled at ``SAMPLE_FPS``: ``{"w", "h", "duration", "frames": [(t, tokens)]}``."""
    from concurrent.futures import ThreadPoolExecutor

    w, h, duration = probe_video(video)
    with tempfile.TemporaryDirectory() as tmp:
        frames = _extract_frames(video, Path(tmp), SAMPLE_FPS)
        with ThreadPoolExecutor(max_workers=6) as pool:
            ocr = list(pool.map(lambda item: (item[0], _ocr_tokens(item[1])), frames))
    return {"w": w, "h": h, "duration": duration, "frames": ocr}


def _latin(text: str) -> bool:
    return len(re.findall(r"[A-Za-z]", text)) >= 2


def _text_groups(tokens: list[dict]) -> list[dict]:
    """Group OCR tokens into text blocks (words on one row, close together)."""
    groups: list[list[dict]] = []
    for tok in sorted(tokens, key=lambda t: (t["y"], t["x"])):
        for group in groups:
            box = _union(group)
            row_h = max(t["h"] for t in group)
            same_row = abs((tok["y"] + tok["h"] / 2) - (box["y"] + box["h"] / 2)) < 0.7 * max(row_h, tok["h"])
            gap = max(box["x"] - (tok["x"] + tok["w"]), tok["x"] - (box["x"] + box["w"]))
            if same_row and gap < 1.6 * max(row_h, tok["h"]):
                group.append(tok)
                break
        else:
            groups.append([tok])
    return [_union(g) for g in groups]


def english_regions(scan: dict) -> list[dict]:
    """Every English text block large enough to read, as ``{"start", "end", "box"}``.

    Burned-in text only: glyphs with a thick dark outline (social captions)
    and large all-caps words; text on screens in the footage is left alone.
    The same block seen in consecutive samples continues one window.
    """
    w, h = scan["w"], scan["h"]
    min_h = 0.02 * h
    half = 0.5 / SAMPLE_FPS
    open_: list[dict] = []
    done: list[dict] = []
    for t, tokens in scan["frames"]:
        # Burned-in overlay text: outlined caption glyphs, or large all-caps words.
        latin = [tok for tok in tokens if tok.get("outlined") or (
            tok["h"] >= 0.025 * h and _latin(tok["text"]) and _is_caps(tok["text"]))]
        for box in _text_groups(latin):
            if box["h"] > _MAX_CAPTION_H * h or box["w"] < 0.03 * w:
                continue
            nb = _normalized(box, w, h)
            # Only the same text block continues a window: captions change
            # every few words and each cover should fit its own words.
            match = next((o for o in open_ if t - half - o["end"] < 0.3
                          and abs(o["box"]["cy"] - nb["cy"]) < 0.015
                          and abs(o["box"]["cx"] - nb["cx"]) < 0.03
                          and abs(o["box"]["w"] - nb["w"]) < 0.15 * max(o["box"]["w"], nb["w"])), None)
            if match:
                ob = match["box"]
                x0 = min(ob["cx"] - ob["w"] / 2, nb["cx"] - nb["w"] / 2)
                x1 = max(ob["cx"] + ob["w"] / 2, nb["cx"] + nb["w"] / 2)
                y0 = min(ob["cy"] - ob["h"] / 2, nb["cy"] - nb["h"] / 2)
                y1 = max(ob["cy"] + ob["h"] / 2, nb["cy"] + nb["h"] / 2)
                match["box"] = {"cx": (x0 + x1) / 2, "cy": (y0 + y1) / 2, "w": x1 - x0, "h": y1 - y0}
                match["end"] = t + half
            else:
                open_.append({"start": t - half, "end": t + half, "box": nb})
        done += [o for o in open_ if o["end"] < t - half - 0.3]
        open_ = [o for o in open_ if o["end"] >= t - half - 0.3]
    regions = done + open_
    return [{"start": round(max(0.0, r["start"]), 3), "end": round(r["end"], 3),
             "box": {k: round(v, 5) for k, v in r["box"].items()}}
            for r in sorted(regions, key=lambda r: r["start"])]


def source_headline(scan: dict) -> str:
    """Read the prominent opening headline for title generation.

    Only large Latin text in the upper opening area is considered, so laptop
    UI text and the later tutorial captions do not become the suggested hook.
    """
    w, h = scan["w"], scan["h"]
    candidates: list[str] = []
    for t, tokens in scan.get("frames", []):
        if t > min(6.0, float(scan.get("duration") or 0.0)):
            break
        top = [tok for tok in tokens if not tok.get("outlined") and _latin(tok.get("text", ""))
               and tok["h"] >= 0.018 * h and tok["y"] + tok["h"] < 0.24 * h]
        rows: list[list[dict]] = []
        for tok in sorted(top, key=lambda item: (item["y"], item["x"])):
            row = next((r for r in rows if abs((tok["y"] + tok["h"] / 2)
                       - _median([x["y"] + x["h"] / 2 for x in r])) < 0.7 * max(tok["h"], _median([x["h"] for x in r]))), None)
            if row is None:
                rows.append([tok])
            else:
                row.append(tok)
        useful = []
        for row in rows:
            box = _union(row)
            text = " ".join(tok["text"].strip() for tok in sorted(row, key=lambda item: item["x"]) if tok["text"].strip())
            if box and box["w"] >= 0.18 * w and len(re.findall(r"[A-Za-z]", text)) >= 8:
                useful.append((box["y"], text))
        if useful:
            candidates.append(" ".join(text for _, text in sorted(useful)))
    if not candidates:
        return ""
    # The earliest readable frame is the cleanest representation of the
    # opening headline; movement later in the hook splits glyphs into noise.
    return candidates[0][:180]


def detect_layout(video: Path, lines: list[dict], words: Optional[list[dict]] = None,
                  scan: Optional[dict] = None) -> tuple[Optional[dict], list[dict]]:
    """Find the burned-in English title and captions.

    Returns ``(title, per_line)`` in normalised frame units. ``title`` is
    ``{"box", "start", "end"}`` (where the English title is on screen) and each
    ``per_line`` item is ``{"box": caption position or None, "covers": [...]}``
    with ``covers`` listing ``{"start", "end", "box"}`` windows, because burned
    captions change every few words and can jump position inside one line.

    Frames are OCR'd at ``SAMPLE_FPS`` and matched against the words spoken
    within 1.5 s of each frame, so laptop-screen text in the footage is not
    mistaken for a caption.
    """
    scan = scan or ocr_video(video)
    w, h, duration, ocr = scan["w"], scan["h"], scan["duration"], scan["frames"]
    min_h = 0.022 * h
    timed_words = [
        (float(wd["start"]), _norm(str(wd.get("w", ""))))
        for wd in (words or []) if len(_norm(str(wd.get("w", "")))) >= 2
    ]
    first_speech = next((l["start"] for l in lines if l.get("kind") != "lyrics"), duration)
    caption_windows: list[dict] = []
    title_frames: list[tuple[float, dict]] = []
    half = 0.5 / SAMPLE_FPS
    for t, tokens in ocr:
        tokens = [tok for tok in tokens if not tok.get("outlined")]
        if timed_words:
            vocab = {word for start, word in timed_words if abs(start - t) <= 1.5}
        else:
            line = next((l for l in lines if l["start"] - 0.5 <= t <= l["end"] + 0.5), None)
            vocab = {_norm(x) for x in (line["en"].split() if line else []) if len(_norm(x)) >= 2}
        hits = _caption_hits(tokens, vocab, min_h, w, h) if vocab else []
        if hits:
            box = _normalized(_union(hits), w, h)
            if box["h"] <= _MAX_CAPTION_H:
                # All-caps text is the burned caption style; mixed case is
                # usually on-screen UI that shares a spoken word.
                caps = any(_is_caps(t["text"]) for t in hits)
                spoken = sorted({_norm(t["text"]) for t in hits if _matches(t["text"], vocab)})
                caption_windows.append({"start": t - half, "end": t + half, "box": box,
                                        "caps": caps, "words": spoken})
        if t < min(first_speech, 15.0):
            big = [tok for tok in tokens if tok["h"] >= 0.03 * h and tok["y"] + tok["h"] < 0.45 * h]
            box = _union(big)
            if box and box["w"] >= 0.12 * w:
                title_frames.append((t, _normalized(box, w, h)))
    caption_windows = _merge_windows(caption_windows)

    results: list[dict] = []
    for line in lines:
        covers = [c for c in caption_windows if c["end"] > line["start"] - 0.2 and c["start"] < line["end"] + 0.2]
        main = None
        if covers:
            main = {key: _median([c["box"][key] for c in covers]) for key in ("cx", "cy", "w", "h")}
        results.append({"box": main, "covers": [
            {"start": round(c["start"], 3), "end": round(c["end"], 3), "box": c["box"],
             "caps": bool(c.get("caps")), "words": c.get("words", [])} for c in covers
        ]})

    title = None
    if title_frames:
        boxes = [b for _, b in title_frames]
        title = {
            "box": {"cx": 0.5, "cy": _median([b["cy"] for b in boxes]),
                    "w": max(b["w"] for b in boxes), "h": _median([b["h"] for b in boxes])},
            "start": 0.0,
            "end": round(max(t for t, _ in title_frames) + 1.0, 3),
        }
    # Lines whose caption OCR found nothing inherit the previous position.
    previous = None
    for item in results:
        if item["box"] is None:
            item["box"] = previous
        previous = item["box"] or previous
    return title, results


# --- timing -----------------------------------------------------------------

def place_clips(lines: list[dict], clips: dict[int, tuple[Path, float]], duration: float) -> list[dict]:
    """Assign start time and tempo to each voice clip.

    A clip starts at its English line start (or right after the previous clip)
    and is sped up, at most ``MAX_TEMPO``, to finish before the next line.
    """
    spoken = [l for l in lines if l["i"] in clips]
    placements = []
    cursor = 0.0
    for idx, line in enumerate(spoken):
        path, length = clips[line["i"]]
        start = line["start"] if idx == 0 else max(line["start"], cursor + 0.05)
        # The last clip (usually the CTA) may run up to 2 s past the source;
        # render() holds the final frame for it.
        limit = spoken[idx + 1]["start"] if idx + 1 < len(spoken) else duration + 2.0
        room = max(0.3, limit - start - 0.05)
        tempo = min(MAX_TEMPO, max(1.0, length / room))
        end = start + length / tempo
        placements.append({"i": line["i"], "file": str(path), "start": round(start, 3),
                           "end": round(end, 3), "tempo": round(tempo, 3)})
        cursor = end
    return placements


# --- ASS --------------------------------------------------------------------

def _ass_colour(hex_colour: str, alpha: int = 0) -> str:
    h = hex_colour.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


# The caption font's space glyph is nearly zero wide, so words (and Persian
# next to Latin, e.g. «تو dropship.io از») ran together; two no-break
# spaces give a normal gap.
WORD_SPACE = "\u00a0\u00a0"


def _escape(text: str) -> str:
    text = text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")
    return re.sub(r"[ \u00a0]+", WORD_SPACE, text.strip())


def _font_metrics(font_file: Optional[Path], size: int) -> tuple[int, int]:
    """(ascent, descent) in pixels, as FreeType/libass lay out one line."""
    try:
        from PIL import ImageFont

        if font_file and font_file.is_file():
            return ImageFont.truetype(str(font_file), size).getmetrics()
    except Exception:
        pass
    return int(size * 0.95), int(size * 0.35)


def measure_text_boxes(texts: list[tuple[str, int]], W: int, H: int, font: str,
                       fonts_dir: Optional[Path]) -> list[tuple[int, int, int]]:
    """Ink (width, top, bottom) in pixels of each single-line (text, font size).

    ``top``/``bottom`` are relative to the line's ``\\an5`` anchor. Persian
    needs real shaping to measure, so render every line once on a black
    canvas with the same libass/font setup as the final video.
    """
    def guess(text: str, size: int) -> tuple[int, int, int]:
        return int(len(text) * size * 0.5), -int(size * 0.45), int(size * 0.35)

    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None or not texts:
        return [guess(t, size) for t, size in texts]
    from PIL import Image

    step = 0.2
    events = [
        f"Dialogue: 0,{_ass_time(k * step)},{_ass_time(k * step + step * 0.9)},m,,0,0,0,,"
        f"{{\\an5\\pos({W / 2:.0f},{H / 2:.0f})\\fs{size}}}{_escape(text)}"
        for k, (text, size) in enumerate(texts)
    ]
    ass = "\n".join([
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: m,{font},40,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,-1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]) + "\n"
    out: list[tuple[int, int, int]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        (tmp_dir / "m.ass").write_text(ass, encoding="utf-8")
        duration = len(texts) * step
        subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:r={1 / step}:d={duration}",
             "-vf", subtitles_filter(tmp_dir / "m.ass", fonts_dir), str(tmp_dir / "m_%04d.png")],
            capture_output=True,
        )
        for k, (text, size) in enumerate(texts):
            frame = tmp_dir / f"m_{k + 1:04d}.png"
            bbox = Image.open(frame).convert("L").point(lambda v: 255 if v > 60 else 0).getbbox() if frame.is_file() else None
            out.append((bbox[2] - bbox[0], bbox[1] - H // 2, bbox[3] - H // 2) if bbox else guess(text, size))
    return out


def measure_text_widths(texts: list[tuple[str, int]], W: int, H: int, font: str,
                        fonts_dir: Optional[Path]) -> list[int]:
    """Rendered width in pixels of each (text, font size)."""
    return [w for w, _, _ in measure_text_boxes(texts, W, H, font, fonts_dir)]


def caption_row(state: dict) -> float:
    """One caption height for the whole video: where the English captions mostly sit."""
    if state.get("caption_y"):
        return float(state["caption_y"])
    samples = []
    for line in state.get("lines", []):
        for c in line.get("covers") or []:
            samples += [c["box"]["cy"]] * max(1, int((c["end"] - c["start"]) * 10))
    y = _median(samples) if samples else DEFAULT_CAPTION_Y
    title = ((state.get("title_layout") or {}).get("box") or {})
    floor = title.get("cy", DEFAULT_TITLE_Y) + title.get("h", 0.03) / 2 + 0.08
    return min(0.85, max(floor, y))


WRAP_FRACTION = 0.8             # lines wider than this share of the frame wrap to two


def _split_balanced(text: str) -> list[str]:
    """Split at the space nearest the middle (by characters)."""
    spaces = [k for k, c in enumerate(text) if c == " "]
    if not spaces:
        return [text]
    cut = min(spaces, key=lambda k: abs(k - len(text) / 2))
    return [text[:cut].strip(), text[cut + 1:].strip()]


def layout_texts(texts: list[tuple[str, int]], W: int, H: int, font: str, fonts_dir: Optional[Path],
                 *, max_w: float, min_size: int) -> list[tuple[list[str], list[int], int]]:
    """Lines, their measured widths and the font size for each (text, size).

    ``\\n`` in a text is an explicit line break. A single line wider than
    ``WRAP_FRACTION`` of the frame wraps to two balanced lines; anything still
    wider than ``max_w`` is shrunk.
    """
    split = [[part.strip() for part in text.split("\n") if part.strip()] or [""] for text, _ in texts]
    flat = [(line, size) for lines, (_, size) in zip(split, texts) for line in lines]
    widths = iter(measure_text_widths(flat, W, H, font, fonts_dir))
    measured = [[next(widths) for _ in lines] for lines in split]
    wrap = [k for k, lines in enumerate(split) if len(lines) == 1 and measured[k][0] > WRAP_FRACTION * W
            and " " in lines[0]]
    if wrap:
        halves = {k: _split_balanced(split[k][0]) for k in wrap}
        flat = [(part, texts[k][1]) for k in wrap for part in halves[k]]
        widths = iter(measure_text_widths(flat, W, H, font, fonts_dir))
        for k in wrap:
            split[k] = halves[k]
            measured[k] = [next(widths) for _ in halves[k]]
    out = []
    for lines, ws, (_, size) in zip(split, measured, texts):
        new = size
        while max(ws) * new / size > max_w and new > min_size:
            new = max(min_size, int(new * 0.92))
        out.append((lines, [int(w * new / size) for w in ws], new))
    return out


def _rounded_rect(layer: int, t0: float, t1: float, x0: float, y0: float, x1: float, y1: float,
                  colour: str, radius: float, extra: str = "") -> str:
    """ASS drawing event for a filled rounded rectangle."""
    w, h = x1 - x0, y1 - y0
    r = min(radius, w / 2, h / 2)
    k = r * 0.45   # bezier handle for a quarter circle
    path = (f"m {r:.1f} 0 l {w - r:.1f} 0 b {w - k:.1f} 0 {w:.1f} {k:.1f} {w:.1f} {r:.1f} "
            f"l {w:.1f} {h - r:.1f} b {w:.1f} {h - k:.1f} {w - k:.1f} {h:.1f} {w - r:.1f} {h:.1f} "
            f"l {r:.1f} {h:.1f} b {k:.1f} {h:.1f} 0 {h - k:.1f} 0 {h - r:.1f} "
            f"l 0 {r:.1f} b 0 {k:.1f} {k:.1f} 0 {r:.1f} 0")
    return (f"Dialogue: {layer},{_ass_time(t0)},{_ass_time(t1)},plain,,0,0,0,,"
            f"{{\\an7\\pos({x0:.1f},{y0:.1f})\\1c&H{_ass_colour(colour)[4:]}&\\1a&H00&\\bord0\\shad0{extra}\\p1}}"
            f"{path}{{\\p0}}")


def end_card_events(cta_number: str, t0: float, t1: float, W: int, H: int, *,
                    fonts_dir: Optional[Path] = None, radius: float = 16.0) -> list[str]:
    """Large, aligned two-line CTA with no text background."""
    n = cta_number.strip() or "31"
    lines = [line.format(n=n) for line in END_CARD_LINES]
    base = size = int(H * 0.050)
    inks = measure_text_boxes([(l, size) for l in lines], W, H, END_CARD_FONT, fonts_dir)
    widest = max(w for w, _, _ in inks)
    if widest > W * 0.90:
        size = int(size * W * 0.90 / widest)
        inks = [(int(w * size / base), int(a * size / base), int(b * size / base)) for w, a, b in inks]
        widest = max(w for w, _, _ in inks)
    pitch = 1.45 * size
    cy = H * 0.47
    anchors = [cy - pitch / 2, cy + pitch / 2]
    fade = "\\fad(350,0)"
    gold = f"\\1c&H{_ass_colour(END_CARD_HIGHLIGHT)[4:]}&"
    white = f"\\1c&H{_ass_colour(TEXT_COLOUR)[4:]}&"
    # Line 1: "عدد" stays white, the ask from the number on is gold.
    head, _, rest = lines[0].partition(" ")
    first = f"{_escape(head)}{WORD_SPACE}{{{gold}}}{_escape(rest)}"
    events = []
    for text, y in ((first, anchors[0]), (_escape(lines[1]), anchors[1])):
        events.append(f"Dialogue: 6,{_ass_time(t0)},{_ass_time(t1)},card,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f})\\fs{size}{white}{fade}}}{text}")
    return events


def render_end_card(out: Path, W: int, H: int, logo: Optional[Path]) -> Path:
    """Background of the end card: charcoal with a faint hand-drawn grid and the logo."""
    import math

    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), END_CARD_BG)
    draw = ImageDraw.Draw(img)
    cell = 75 * W / 1080
    width = max(1, round(2 * W / 1080))
    amp = 2.5 * W / 1080
    x = cell / 2
    while x < W:
        phase = x * 0.013
        draw.line([(x + amp * math.sin(y / 160 + phase), y) for y in range(0, H + 20, 20)],
                  fill=END_CARD_GRID, width=width)
        x += cell
    y = cell / 2
    while y < H:
        phase = y * 0.011
        draw.line([(x2, y + amp * math.sin(x2 / 140 + phase)) for x2 in range(0, W + 20, 20)],
                  fill=END_CARD_GRID, width=width)
        y += cell
    if logo and logo.is_file():
        mark = Image.open(logo).convert("RGBA")
        mh = int(H * 0.04)
        mark = mark.resize((int(mark.width * mh / mark.height), mh), Image.LANCZOS)
        img.paste(mark, ((W - mark.width) // 2, int(H * 0.70)), mark)
    img.save(out)
    return out


def plan_overlays(state: dict, placements: list[dict], W: int, H: int, duration: float, *,
                  font: str = "Ray ExtraBlack", font_file: Optional[Path] = None,
                  fonts_dir: Optional[Path] = None, source_duration: Optional[float] = None,
                  end_card_at: Optional[float] = None) -> str:
    """Return the ASS text for the title, captions and the end card.

    Every Persian box (title, captions, CTA) hugs its measured text with a
    small padding, wrapping to two lines past ``WRAP_FRACTION`` of the
    frame. Each caption sits on the English caption shown during it and
    hides the English on its row by growing its text, so the box stays
    full. There are no other boxes: brief English elsewhere stays visible
    rather than adding boxes around the caption.

    With ``end_card_at`` the video cuts to the end card (see
    ``render_end_card``) at that time: captions stop there and the card's
    CTA box and text are added on top of it.
    """
    text_colour = _ass_colour(TEXT_COLOUR)
    caption_style = BOX_STYLES.get(state.get("caption_box") or "", BOX_STYLES["black"])
    title_style = BOX_STYLES.get(state.get("title_box") or "", caption_style)
    cover_pad = int(H * 0.006)
    radius = 13 * W / 1080
    source_duration = source_duration if source_duration is not None else duration
    end_all = max(0.01, (end_card_at if end_card_at is not None else duration) - 0.02)

    # Persian lines and their on-screen windows (never overlapping).
    by_index = {p["i"]: p for p in placements}
    shown = [l for l in state.get("lines", []) if l.get("kind") != "lyrics" and l.get("fa")
             and (by_index.get(l["i"]) or l)["start"] < end_all]
    windows = []
    for k, line in enumerate(shown):
        placed = by_index.get(line["i"])
        start = placed["start"] if placed else line["start"]
        stop = (placed["end"] if placed else line["end"]) + 0.2
        if k + 1 < len(shown):
            nxt = by_index.get(shown[k + 1]["i"])
            nxt_start = nxt["start"] if nxt else shown[k + 1]["start"]
            # Bridge short pauses so the caption row never shows a bare cover.
            stop = nxt_start if nxt_start - stop < 1.5 else min(stop, nxt_start)
        if k == len(shown) - 1:
            stop = end_all
        windows.append((line, start, min(stop, end_all)))

    # Large bold text (about 70-80 px at 1080 wide) in a box that hugs it.
    # The text grows (up to about 100 px at 1080 wide) to fill a box that
    # must hide a large English caption, instead of the box padding out.
    base_size, min_size, max_size = int(H * 0.031), int(H * 0.024), int(H * 0.052)
    max_text_w = W * MAX_TEXT_FRACTION
    title_text = (state.get("title") or "").strip()
    texts = [(line["fa"], base_size) for line, _, _ in windows] + ([(title_text, base_size)] if title_text else [])
    layouts = layout_texts(texts, W, H, font, fonts_dir, max_w=max_text_w, min_size=min_size)
    flat = [(l, size) for lines, _, size in layouts for l in lines]
    inks = iter(measure_text_boxes(flat, W, H, font, fonts_dir))
    ink_rows = [[next(inks)[1:] for _ in lines] for lines, _, _ in layouts]

    # The matched caption windows define both placement and coverage. This
    # avoids turning unrelated UI or headline text into giant black panels.
    captions = [c for line in state.get("lines", []) for c in (line.get("covers") or [])]
    row_y = caption_row(state) * H
    covers = list(captions)
    if source_duration < duration:
        # The source's last frame is held; so is the text burned into it.
        covers, captions = ([{**c, "end": duration} if c["end"] >= source_duration - 0.4 else c for c in group]
                            for group in (covers, captions))

    events: list[str] = []

    def rect(layer: int, t0: float, t1: float, x0: float, y0: float, x1: float, y1: float, colour: str) -> None:
        events.append(_rounded_rect(layer, t0, t1, x0, y0, x1, y1, colour, radius))

    def text(layer: int, t0: float, t1: float, y: float, line: str, size: int, colour: str) -> None:
        events.append(f"Dialogue: {layer},{_ass_time(t0)},{_ass_time(t1)},caption,,0,0,0,,"
                      f"{{\\an5\\q2\\pos({W / 2:.0f},{y:.1f})\\fs{size}\\1c&H{_ass_colour(colour)[4:]}&}}"
                      + _escape(line))

    def block(lines_ink: list[tuple[int, int]], size: int, layout_size: int, cy: float
              ) -> tuple[list[float], float, float]:
        """Line anchors and ink top/bottom of a text block centred on ``cy``."""
        f = size / layout_size
        pitch = LINE_PITCH * size
        anchors = [k * pitch for k in range(len(lines_ink))]
        top = anchors[0] + lines_ink[0][0] * f
        bottom = anchors[-1] + lines_ink[-1][1] * f
        shift = cy - (top + bottom) / 2
        return [a + shift for a in anchors], top + shift, bottom + shift

    def place(layer: int, t0: float, t1: float, cy: float, item: int, style: tuple[str, str],
              *, absorb: tuple[float, float], floor: float = 0.0, reach: float = 0.0) -> tuple[float, float]:
        """Draw a tight text box and time-matched covers for source captions."""
        lines, widths, layout_size = layouts[item]
        lines_ink = ink_rows[item]

        def extents(size: int) -> tuple[float, float, float, list[float]]:
            pad_x, pad_y = PAD_X * size, PAD_Y * size
            anchors, top, bottom = block(lines_ink, size, layout_size, cy)
            return max(widths) * size / layout_size / 2 + pad_x, top - pad_y, bottom + pad_y, anchors

        half, top, bottom, anchors = extents(layout_size)
        margin = H * 0.01
        hit: set[int] = set()
        for k, c in enumerate(covers):
            if c["end"] <= absorb[0] or c["start"] >= absorb[1]:
                continue
            bx = c["box"]
            y0, y1 = (bx["cy"] - bx["h"] / 2) * H - cover_pad, (bx["cy"] + bx["h"] / 2) * H + cover_pad
            band_top, band_bottom = top - margin - reach, bottom + margin + reach
            if min(y1, band_bottom) - max(y0, band_top) < 0.35 * (y1 - y0) or y0 < floor:
                continue
            hit.add(k)
        size = layout_size
        box_colour, text_col = style
        # Each changing English caption gets its own short-lived exact cover;
        # it no longer inflates the Persian box for the entire sentence.
        for k in hit:
            c, bx = covers[k], covers[k]["box"]
            # Keep the detected width so no English letters remain at the
            # sides; only cap the noisy vertical union that caused huge margins.
            cover_w = bx["w"] * W + 2 * cover_pad
            cover_h = min(bx["h"] * H + 2 * cover_pad, max((bottom - top) * 1.25, H * 0.045))
            cover_cx, cover_cy = bx["cx"] * W, bx["cy"] * H
            rect(layer, max(t0, c["start"]), min(t1, c["end"]),
                 cover_cx - cover_w / 2, max(floor, cover_cy - cover_h / 2),
                 cover_cx + cover_w / 2, cover_cy + cover_h / 2, box_colour)
        rect(layer, t0, t1, W / 2 - half, top, W / 2 + half, bottom, box_colour)
        for line, y in zip(lines, anchors):
            text(layer + 1, t0, t1, y, line, size, text_col)
        return top, bottom

    title_box = (state.get("title_layout") or {}).get("box")
    title_y = (title_box or {}).get("cy", DEFAULT_TITLE_Y) * H
    if title_box:
        title_y = (title_box["cy"] + title_box["h"] / 2) * H + base_size * 0.8
    title_bottom = 0.0
    if title_text:
        first_tutorial = next((float(line["start"]) for line in state.get("lines", [])
                               if line.get("kind") != "lyrics"), 4.0)
        title_end = min(8.0, max(3.0, first_tutorial - 0.25))
        _, title_bottom = place(1, 0, title_end, title_y, len(layouts) - 1, title_style,
                                absorb=(0.0, 0.0))
        title_bottom += H * 0.01

    title_floor = title_bottom
    previous_y = row_y
    for k, (line, t0, t1) in enumerate(windows):
        lines, _, size = layouts[k]
        bh = (len(lines) * LINE_PITCH + 2 * PAD_Y) * size
        # Sit on the English caption shown longest during this line
        # (constant for the whole line), else keep the previous position.
        nearby = [c for c in captions if c["end"] > t0 - 0.25 and c["start"] < t1 + 0.25]
        if nearby:
            def overlap(c):
                return max(0.0, min(c["end"], t1 + 0.25) - max(c["start"], t0 - 0.25))

            # Prefer all-caps caption text over screen UI that shares a word,
            # and the usual caption row over one-off positions (on-screen
            # headings are often all caps too): an off-row position must
            # cover at least half of the line and beat the row to move it.
            styled = [c for c in nearby if c.get("caps")] or nearby
            on_row = [c for c in styled if abs(c["box"]["cy"] * H - row_y) < H * 0.06]
            # Off-row text only counts when it shows words of this very line
            # (an on-screen heading can match the previous line's words).
            line_vocab = {_norm(w) for w in (line.get("words") or line.get("en", "").split()) if len(_norm(w)) >= 2}
            off_row = [c for c in styled if c not in on_row
                       and any(_matches(w, line_vocab) for w in c.get("words", []))]
            best_on = max(on_row, key=overlap, default=None)
            best_off = max(off_row, key=overlap, default=None)
            span = max(0.1, t1 - t0)
            if best_off and overlap(best_off) >= 0.5 * span and (
                    best_on is None or overlap(best_off) > 2 * overlap(best_on)):
                main = best_off["box"]
            else:
                main = best_on["box"] if best_on else {"cy": row_y / H}
            line_y = min(max(main["cy"] * H, title_floor + bh / 2), H * 0.9 - bh / 2)
        else:
            line_y = max(previous_y, title_floor + bh / 2)
        previous_y = line_y
        # The CTA is the last thing on screen: it also hides the English
        # CTA's other rows (e.g. COMMENT "G" above FOR A FREE DM).
        reach = 0.0
        if line.get("kind") == "cta":
            reach = H * 0.07
            rows = [c["box"] for c in covers if c["end"] > t0 and c["start"] < t1
                    and abs(c["box"]["cy"] * H - line_y) < reach + bh / 2]
            if rows:   # centre on the whole English CTA
                line_y = max(title_floor + bh / 2, (min((b["cy"] - b["h"] / 2) for b in rows)
                                                    + max((b["cy"] + b["h"] / 2) for b in rows)) / 2 * H)
        place(3, t0, t1, line_y, k, caption_style, absorb=(t0, t1), floor=title_floor, reach=reach)

    if end_card_at is not None:
        events += end_card_events(str(state.get("cta_number") or ""), end_card_at, duration, W, H,
                                  fonts_dir=fonts_dir, radius=16 * W / 1080)

    header = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: caption,{font},{base_size},{text_colour},&H000000FF,&H00000000,&H00000000,-1,0,0,0,"
        f"100,100,0,0,1,0,0,5,0,0,0,-1",
        "Style: plain,Arial,10,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1",
        f"Style: card,{END_CARD_FONT},{base_size},{text_colour},&H000000FF,&H00000000,&H00000000,-1,0,0,0,"
        f"100,100,0,0,1,0,0,5,0,0,0,-1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    return "\n".join(header + events) + "\n"



# --- emoji ------------------------------------------------------------------

def render_emoji_png(emojis: str, out: Path, height: int) -> Optional[Path]:
    if not emojis.strip() or not EMOJI_FONT.is_file():
        return None
    try:
        from PIL import Image, ImageDraw, ImageFont

        font = ImageFont.truetype(str(EMOJI_FONT), 160)
        canvas = Image.new("RGBA", (200 * max(1, len(emojis)), 200))
        ImageDraw.Draw(canvas).text((0, 0), emojis, font=font, embedded_color=True)
        bbox = canvas.getbbox()
        if not bbox:
            return None
        img = canvas.crop(bbox)
        img = img.resize((max(1, int(img.width * height / img.height)), height))
        img.save(out)
        return out
    except Exception:
        log.warning("emoji rendering failed", exc_info=True)
        return None


# --- render -----------------------------------------------------------------

def audio_cut_time(lines: list[dict], placements: list[dict]) -> float:
    """Original audio plays until the first Persian clip (e.g. an intro song)."""
    if not placements:
        return 0.0
    return max(0.0, min(p["start"] for p in placements) - 0.15)


def render(
    video: Path,
    state: dict,
    placements: list[dict],
    out: Path,
    *,
    work_dir: Path,
    fonts_dir: Optional[Path] = None,
    music: Optional[Path] = None,
    logo: Optional[Path] = None,
    on_progress: Optional[Callable[[int], None]] = None,
) -> Path:
    ffmpeg = ass_burner_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("Localized rendering needs an ffmpeg with libass (brew install ffmpeg-full)")
    src_w, src_h, source_duration = probe_video(video)
    W, H = output_size(src_w, src_h)
    voice_end = max((p["end"] for p in placements), default=0.0) + 0.5
    end_card = state.get("end_card", True)
    if end_card:
        # Cut to the end card when the source ends; the CTA voice runs on.
        card_seconds = float(state.get("end_card_seconds") or END_CARD_SECONDS)
        duration = max(source_duration + card_seconds, voice_end)
    else:
        # A Persian CTA can outrun the English one; hold the last frame for it.
        duration = max(source_duration, voice_end)
    hold = max(0.0, duration - source_duration)
    work_dir.mkdir(parents=True, exist_ok=True)
    ass = work_dir / "localized.ass"
    font_file = (fonts_dir / "RAY-EXTRABLACK.TTF") if fonts_dir else None
    ass_text = plan_overlays(state, placements, W, H, duration, font_file=font_file,
                             fonts_dir=fonts_dir, source_duration=source_duration,
                             end_card_at=source_duration if end_card else None)
    ass.write_text(ass_text, encoding="utf-8")

    inputs = ["-i", str(video)]
    fps = probe_fps(video)
    n = 1
    if end_card:
        card = render_end_card(work_dir / "end_card.png", W, H, logo)
        inputs += ["-loop", "1", "-framerate", f"{fps}", "-t", f"{hold:.3f}", "-i", str(card)]
        vf = [f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1,fps={fps},format=yuv420p[src]",
              f"[1:v]scale={W}:{H},setsar=1,fps={fps},format=yuv420p[card]",
              "[src][card]concat=n=2:v=1:a=0[base]"]
        n = 2
    else:
        pad_video = f",tpad=stop_mode=clone:stop_duration={hold:.3f}" if hold > 0.01 else ""
        vf = [f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1{pad_video}[base]"]
    last = "base"
    vf.append(f"[{last}]{subtitles_filter(ass, fonts_dir)}[v0]")
    last = "v0"
    # Emoji and logo belong to the source part; the end card has its own logo.
    only_source = f":enable='lt(t,{source_duration:.3f})'" if end_card else ""
    ty = ((state.get("title_layout") or {}).get("box") or {}).get("cy", DEFAULT_TITLE_Y) * H
    emoji_text = "" if state.get("title_layout") else state.get("title_emojis", "")
    emoji = render_emoji_png(emoji_text, work_dir / "emoji.png", int(H * 0.045))
    if emoji:
        inputs += ["-i", str(emoji)]
        y = max(0, int(ty - H * 0.034 / 2 - H * 0.009 - H * 0.05))
        vf.append(f"[{last}][{n}:v]overlay=x=(W-w)/2:y={y}{only_source}[v{n}]")
        last, n = f"v{n}", n + 1
    if logo and logo.is_file():
        inputs += ["-i", str(logo)]
        vf.append(f"[{n}:v]scale=-1:{int(H * 0.04)}[logo]")
        vf.append(f"[{last}][logo]overlay=x=(W-w)/2:y={int(H * 0.80)}{only_source}[v{n}]")
        last, n = f"v{n}", n + 1

    cut = audio_cut_time(state.get("lines", []), placements)
    af = []
    mix = []
    if cut > 0.05:
        fade = min(0.3, cut)
        af.append(f"[0:a]atrim=0:{cut:.3f},afade=t=out:st={cut - fade:.3f}:d={fade:.3f},"
                  f"aresample=48000[orig]")
        mix.append("[orig]")
    has_music = bool(music and music.is_file())
    if has_music:
        inputs += ["-stream_loop", "-1", "-i", str(music)]
        length = max(0.1, duration - cut)
        af.append(f"[{n}:a]atrim=0:{length:.3f},volume={MUSIC_VOLUME_DB}dB,"
                  f"afade=t=in:st=0:d=0.6,afade=t=out:st={max(0.0, length - 1.2):.3f}:d=1.2,"
                  f"aresample=48000,aformat=channel_layouts=stereo,adelay={int(cut * 1000)}:all=1[music]")
        n += 1
    voice = []
    for k, p in enumerate(placements):
        inputs += ["-i", p["file"]]
        tempo = f"atempo={p['tempo']}," if p["tempo"] > 1.001 else ""
        af.append(f"[{n}:a]{tempo}aresample=48000,aformat=channel_layouts=stereo,"
                  f"adelay={int(p['start'] * 1000)}:all=1[c{k}]")
        voice.append(f"[c{k}]")
        n += 1
    if voice and has_music:
        # Duck the music under the voice.
        af.append(f"{''.join(voice)}amix=inputs={len(voice)}:normalize=0:duration=longest,asplit[vo][key]")
        af.append("[music][key]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=400[ducked]")
        mix += ["[vo]", "[ducked]"]
    else:
        mix += voice + (["[music]"] if has_music else [])
    if not mix:
        af.append("anullsrc=r=48000:cl=stereo[silence]")
        mix.append("[silence]")
    af.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,"
              f"atrim=0:{duration:.3f},loudnorm=I=-14:TP=-1.5,aresample=48000[a]")

    cmd = [ffmpeg, "-hide_banner", "-y", *inputs,
           "-filter_complex", ";".join(vf + af),
           "-map", f"[{last}]", "-map", "[a]",
           "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}",
           "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.stdout is not None
    for row in proc.stdout:
        if row.startswith("out_time_us=") and on_progress and duration > 0:
            try:
                on_progress(min(99, int(int(row.split("=")[1]) / 1e6 / duration * 100)))
            except ValueError:
                pass
    stderr = proc.stderr.read() if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed: {stderr.strip()[-800:]}")
    if on_progress:
        on_progress(100)
    return out

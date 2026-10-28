"""Persian/Arabic text for Pillow builds without libraqm: join the letters (presentation forms) and put them in visual order.

``install(font_path_for_arabic)`` patches ``FreeTypeFont.getbbox/getlength`` and ``ImageDraw.text`` so any text with Arabic-script letters is shaped, and drawn
with the Persian-capable font whatever font the effect asked for (the UI fonts of the effects have no Persian glyphs). When Pillow has raqm the patch only
swaps the font; raqm shapes the text itself.
"""
from __future__ import annotations

import unicodedata

from PIL import ImageDraw, ImageFont, features

_FORMS: dict[str, dict[str, str]] = {}
_LIGA: dict[tuple[str, str], dict[str, str]] = {}
ZWNJ = "‌"


def _build() -> None:
    for cp in list(range(0xFB50, 0xFDFF)) + list(range(0xFE70, 0xFEFD)):
        ch = chr(cp)
        d = unicodedata.decomposition(ch)
        if not d.startswith("<"):
            continue
        tag, *rest = d.split()
        if tag not in ("<isolated>", "<initial>", "<medial>", "<final>"):
            continue
        if len(rest) == 1:
            _FORMS.setdefault(chr(int(rest[0], 16)), {})[tag[1:-1]] = ch
        elif len(rest) == 2 and rest[0] == "0644":
            _LIGA.setdefault((chr(0x0644), chr(int(rest[1], 16))), {})[tag[1:-1]] = ch
    # Persian letters share the Arabic forms of their Arabic twins when the table above lacks them
    for persian, arabic in (("ی", "ي"), ("ک", "ك")):
        if persian not in _FORMS and arabic in _FORMS:
            _FORMS[persian] = _FORMS[arabic]


_build()


def has_arabic(s) -> bool:
    return any("؀" <= ch <= "ۿ" or "ݐ" <= ch <= "ݿ" or "ﭐ" <= ch <= "ﻼ" for ch in str(s))


def _dual(c: str) -> bool:
    return "initial" in _FORMS.get(c, {})


def _joinable(c: str) -> bool:
    return "final" in _FORMS.get(c, {})


def _ltr(c: str) -> bool:
    return c.isascii() and c.isalnum() or "۰" <= c <= "۹" or "٠" <= c <= "٩"


def shape(text: str) -> str:
    """Logical Persian text -> the string to hand to a left-to-right renderer: joined letters, visual order, numbers and Latin kept readable."""
    chars = list(text)
    out: list[str] = []
    i = 0
    while i < len(chars):
        c = chars[i]
        prev = chars[i - 1] if i else ""
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if c == "ل" and (c, nxt) in _LIGA:
            f = _LIGA[(c, nxt)]
            joined_prev = _dual(prev) and prev != ZWNJ
            out.append(f.get("final" if joined_prev else "isolated") or next(iter(f.values())))
            i += 2
            continue
        if c in _FORMS:
            jp = bool(prev) and _dual(prev)
            jn = _dual(c) and bool(nxt) and _joinable(nxt)
            f = _FORMS[c]
            form = "medial" if jp and jn else "final" if jp else "initial" if jn else "isolated"
            out.append(f.get(form) or f.get("isolated") or c)
        elif c != ZWNJ:
            out.append(c)
        i += 1
    # visual order: runs of left-to-right text keep their order, everything else flows right to left
    runs: list[tuple[bool, str]] = []
    for k, c in enumerate(out):
        left = _ltr(c) or (c in ".,:/%-" and 0 < k < len(out) - 1 and _ltr(out[k - 1]) and _ltr(out[k + 1]))
        if runs and runs[-1][0] == left:
            runs[-1] = (left, runs[-1][1] + c)
        else:
            runs.append((left, c))
    return "".join(r if left else r[::-1] for left, r in reversed(runs))


_installed = False


def install(fa_font_path: str) -> None:
    global _installed
    if _installed:
        return
    _installed = True
    raqm = features.check("raqm")
    cache: dict[int, ImageFont.FreeTypeFont] = {}

    def fa_of(f: ImageFont.FreeTypeFont):
        size = int(getattr(f, "size", 40))
        if size not in cache:
            cache[size] = ImageFont.truetype(fa_font_path, size, layout_engine=ImageFont.Layout.RAQM if raqm else ImageFont.Layout.BASIC)
        return cache[size]

    def fix(f, text):
        if isinstance(text, str) and has_arabic(text):
            if getattr(f, "path", None) != fa_font_path:
                f = fa_of(f)
            return f, (text if raqm else shape(text))
        return f, text

    orig_bbox, orig_len = ImageFont.FreeTypeFont.getbbox, ImageFont.FreeTypeFont.getlength

    def getbbox(self, text, *a, **k):
        f, t = fix(self, text)
        return orig_bbox(f, t, *a, **k)

    def getlength(self, text, *a, **k):
        f, t = fix(self, text)
        return orig_len(f, t, *a, **k)

    orig_text = ImageDraw.ImageDraw.text

    def text(self, xy, text, fill=None, font=None, *a, **k):
        if font is not None:
            font, text = fix(font, text)
        return orig_text(self, xy, text, fill, font, *a, **k)

    ImageFont.FreeTypeFont.getbbox = getbbox
    ImageFont.FreeTypeFont.getlength = getlength
    ImageDraw.ImageDraw.text = text

"""The text of a supplied page, without its chrome.

Page extraction returns every visible text node in order, so a long article starts with its site menu, side bar and
table of contents. Cutting the list to "the first 80 items" (what the storyboard prompt used to do) hands the script
writer the menu and none of the article. ``article_text`` finds where the real prose is and returns that.
"""
from __future__ import annotations

import re

_CITATION = re.compile(r"\[\s*[\d۰-۹]+\s*\]|\[\s*(?:نیاز به منبع|توضیح لازم|citation needed)\s*\]")
_SPACE = re.compile(r"\s+")
PROSE_MIN = 80          # characters: shorter nodes are labels, links and list items
MIN_ARTICLE_PROSE = 2   # fewer paragraphs than this and the page is not an article


def _clean(text: str) -> str:
    return _SPACE.sub(" ", _CITATION.sub("", str(text))).strip()


def article_text(page: dict | list, limit: int = 9000) -> str:
    """Prose paragraphs (and the short headings between them) in document order, citation markers removed, capped at ``limit``."""
    items = page.get("content", []) if isinstance(page, dict) else list(page)
    cleaned = [_clean(item) for item in items]
    prose = [i for i, text in enumerate(cleaned) if len(text) >= PROSE_MIN]
    if len(prose) < MIN_ARTICLE_PROSE:
        body = [t for t in cleaned if len(t) >= 20]           # a short page: keep its meaningful lines
    else:
        body = [t for t in cleaned[prose[0]:prose[-1] + 1] if t]
    seen: set[str] = set()
    out, size = [], 0
    for text in body:
        if text in seen:
            continue
        seen.add(text)
        if size + len(text) > limit:
            room = limit - size
            if room > 200:                                    # keep a useful part of the last paragraph
                out.append(text[:room].rsplit(" ", 1)[0] + "…")
            break
        out.append(text)
        size += len(text) + 1
    return "\n".join(out)

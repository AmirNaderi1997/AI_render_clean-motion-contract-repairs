"""Persian text fixes for burned-in subtitles."""
import re

_DISPLAY_DIGITS = str.maketrans("0123456789%.", "۰۱۲۳۴۵۶۷۸۹٪٫")


def display_text(text: str) -> str:
    """Localize numeric tokens, preserving Latin tokens and their next token.

    Applied only at template boundaries: source spelling and alignment stay intact.
    A Latin-bearing whitespace token owns the immediately following numeric token
    (iPhone 15); mixed tokens (A52, 5G) are preserved themselves.
    """
    previous_latin = False

    def token(match):
        nonlocal previous_latin
        value = match.group()
        latin = bool(re.search(r"[A-Za-z]", value))
        result = value if latin or previous_latin else value.translate(_DISPLAY_DIGITS) if re.search(r"[0-9]", value) else value
        previous_latin = latin
        return result

    return re.sub(r"\S+", token, text)


def display_units(text: str) -> list[str]:
    """Whole-word animation units; keep adjacent Latin/model tokens in LTR order."""
    units = []
    run = []
    for word in display_text(text).split():
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.,:+_/%-]*", word):
            run.append(word)
        else:
            if run:
                units.append(" ".join(run))
                run = []
            units.append(word)
    if run:
        units.append(" ".join(run))
    return units

# The Ray fonts shape a lam followed by an alef into a ligature that libass draws with an extra empty box next to it ("بالا", "اصلاً", "سلام").
# A zero-width joiner between the two keeps both letters joined, as separate glyphs, and the box never appears.
_LAM_ALEF = re.compile("(\u0644)(?=[\u0622\u0623\u0625\u0627\u0671])")


def join_lam_alef(text: str) -> str:
    return _LAM_ALEF.sub("\\1\u200d", text)

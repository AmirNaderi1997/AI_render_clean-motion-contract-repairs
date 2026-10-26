"""Persian text fixes for burned-in subtitles."""
import re

# The Ray fonts shape a lam followed by an alef into a ligature that libass draws with an extra empty box next to it ("بالا", "اصلاً", "سلام").
# A zero-width joiner between the two keeps both letters joined, as separate glyphs, and the box never appears.
_LAM_ALEF = re.compile("(\u0644)(?=[\u0622\u0623\u0625\u0627\u0671])")


def join_lam_alef(text: str) -> str:
    return _LAM_ALEF.sub("\\1\u200d", text)

"""Explicit no-edit render requests; never infer consent from a larger edit."""
import re


def is_plain_rerender(text: str) -> bool:
    text=re.sub(r'[.،؛!؟?]+',' ',text).strip().lower()
    text=' '.join(text.split())
    return bool(re.fullmatch(
        r'(?:(?:لطفا|لطفاً) )?(?:(?:مجدد|مجدداً|دوباره|بازم) رندر (?:بگیر|کن)|'
        r'رندر (?:رو |را )?(?:مجدد|دوباره) (?:بگیر|کن)|'
        r'(?:رندر (?:رو |را )?(?:بگیر|کن|بزن)|(?:بزن|شروع کن) رندر|رندر شروع کن)|'
        r'(?:re-?render|render again|render|render it)(?: please)?)',text))

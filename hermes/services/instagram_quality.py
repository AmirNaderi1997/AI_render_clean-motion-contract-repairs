"""Bounded local content checks; no model, network, publishing or file inputs.

English behavior stays upstream. Persian checks deliberately do not use the
English lexicon or its destructive Unicode-format cleanup.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
import unicodedata

VENDOR = Path(__file__).resolve().parents[2] / "vendor" / "instagram-agent-skill"
MAX_TEXT = 20_000
SCRIPTS = {
    "hook": "ig-reel/hookscore.py", "beats": "ig-reel/beats.py",
    "caption": "ig-caption/caption.py", "humanize": "ig-human/humanize.py",
    "audit_text": "ig-human/detect.py", "swipe": "ig-viral/swipe.py",
}
WORDS = re.compile(r"[^\W_]+(?:[\u200c'’][^\W_]+)*", re.UNICODE)
DISCLAIMER = "Local editing heuristics, not a prediction of reach or proof of AI authorship."
# Fixed trusted program: the caller cannot supply a command, path or CLI flags.
RUNNER = """
import resource, runpy, sys
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
resource.setrlimit(resource.RLIMIT_FSIZE, (1048576, 1048576))
path = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(path, run_name='__main__')
"""


def normalize_persian(text: str) -> str:
    # NFC and Arabic keyboard variants only. ZWNJ/ZWJ are meaningful, retained.
    return unicodedata.normalize("NFC", text).translate(str.maketrans("كي", "کی"))


def words(text: str) -> list[str]:
    return WORDS.findall(text)


def persian(operation: str, text: str, wpm: float, target: float | None) -> dict:
    text = normalize_persian(text)
    tokens = words(text)
    warnings = []
    if operation == "humanize":
        # Flag rather than blindly rewrite claims, voice or grammar.
        for phrase in ("در دنیای پرشتاب امروز", "انقلابی در", "سفری به دنیای"):
            if phrase in text:
                warnings.append({"code": "FORMULAIC_PHRASE", "text": phrase})
        return {"text": text, "warnings": warnings, "rewritten": False}
    if operation == "beats":
        clock, rows = 0.0, []
        for line in re.split(r"\n+|(?<=[.!؟?؛])\s+", text):
            count = len(words(line))
            if not count:
                continue
            duration = count * 60 / wpm
            rows.append({"text": line.strip(), "words": count,
                         "start": round(clock, 2), "dur": round(duration, 2),
                         "flags": ["LONG_BEAT"] if duration > 4 else []})
            clock += duration
        return {"beats": rows, "total_seconds": round(clock, 2),
                "total_words": len(tokens), "wpm": wpm, "target": target,
                "timing_is_estimate": True}
    if operation == "caption":
        tags = re.findall(r"(?<!\S)#[\w\u200c]+", text)
        asks = [name for name, pattern in (
            ("save", r"ذخیره (?:کن|کنید)"), ("comment", r"کامنت (?:بذار|بگذار|کن)"),
            ("send", r"(?:بفرست|ارسال کن)"), ("follow", r"(?:دنبال|فالو) (?:کن|کنید)"),
            ("dm", r"دایرکت (?:بده|بدید|بفرست)"),
        ) if re.search(pattern, text)]
        if len(asks) != 1:
            warnings.append({"code": "REVIEW_CTA_COUNT", "count": len(asks)})
        if len(text) > 2200:
            warnings.append({"code": "CAPTION_TOO_LONG"})
        return {"text": text, "characters": len(text), "visible": text[:125],
                "visible_is_approximate": True, "hashtags": tags, "asks": asks,
                "warnings": warnings}
    if operation == "hook":
        duration = len(tokens) * 60 / wpm
        if duration > 3:
            warnings.append({"code": "LONG_HOOK", "estimated_seconds": round(duration, 2)})
        if re.match(r"^(?:سلام|توی این ویدیو|در این ویدیو)", text):
            warnings.append({"code": "PREAMBLE"})
        if not any(char.isdecimal() for char in text):
            warnings.append({"code": "REVIEW_SPECIFICITY", "note": "No numeric marker; not evidence of a weak hook."})
        return {"hook": text, "words": len(tokens), "warnings": warnings,
                "estimated_seconds": round(duration, 2), "score": None}
    raise ValueError("This check has not been adapted for Persian")


def evaluate(operation: str, text: str, language: str, *, wpm=150.0, target=None) -> dict:
    if operation not in SCRIPTS or language not in {"fa", "en"}:
        raise ValueError("Unsupported operation or language")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT or "\x00" in text:
        raise ValueError("Expected non-empty text of at most 20000 characters")
    if not 60 <= wpm <= 300 or (target is not None and not 1 <= target <= 600):
        raise ValueError("Invalid speaking rate or target duration")
    if language == "en" and re.search(r"[\u0600-\u06ff]", text):
        raise ValueError("Use the Persian adapter for Persian or mixed Persian text")
    if language == "fa":
        result = persian(operation, text, wpm, target)
    else:
        command = [sys.executable, "-I", "-S", "-c", RUNNER,
                   str(VENDOR / "skills" / SCRIPTS[operation]), "-", "--json"]
        if operation == "beats":
            command += ["--wpm", str(wpm)]
            if target is not None:
                command += ["--target", str(target)]
        completed = subprocess.run(command, input=text, text=True, capture_output=True,
                                   timeout=8, cwd=VENDOR,
                                   env={"PYTHONIOENCODING": "utf-8", "LANG": "C.UTF-8"})
        # Several upstream checks return 1 for a weak score, not an execution error.
        if completed.returncode not in {0, 1} or len(completed.stdout) > 1_048_576:
            raise RuntimeError("Instagram content check failed")
        try:
            result = json.loads(completed.stdout)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Instagram content check returned invalid data") from exc
    return {"language": language, "operation": operation, "result": result,
            "disclaimer": DISCLAIMER}

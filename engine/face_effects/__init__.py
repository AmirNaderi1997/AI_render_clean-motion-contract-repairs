"""Video effects that follow the speaker (adapted from github.com/Vibha-Ramprakash/claude-video-effects, MIT; see NOTICE.md).

``clean_plan`` validates a list of effects; ``apply`` lays them over a finished video; ``preview`` renders one still frame to check an effect before
the whole video is rendered. The heavy work runs in a child process (``runner``) that is killed on cancel.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

from .catalog import BY_ID, CATALOG, EffectsError, clean_plan

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS = PROJECT_ROOT / "assets" / "effects"
__all__ = ["CATALOG", "BY_ID", "EffectsError", "clean_plan", "apply", "preview", "available"]


def available() -> bool:
    """Is the tracker's runtime installed here (mediapipe)? Without it no effect can be rendered."""
    try:
        import importlib.util
        return importlib.util.find_spec("mediapipe") is not None
    except Exception:
        return False


def _env() -> dict:
    env = dict(os.environ)
    lib = str(ASSETS / "lib")
    env["LD_LIBRARY_PATH"] = lib + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    env["EFFECTS_ASSETS"] = str(ASSETS)
    env.setdefault("OMP_NUM_THREADS", "2")
    env.setdefault("OPENBLAS_NUM_THREADS", "2")
    env["PYTHONPATH"] = str(PROJECT_ROOT) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def _run(args: list[str], *, on_progress: Optional[Callable[[float, str], None]], should_cancel: Optional[Callable[[], bool]], timeout: float) -> tuple[int, str]:
    process = subprocess.Popen([sys.executable, "-m", "engine.face_effects.runner", *args], cwd=str(PROJECT_ROOT), env=_env(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    import threading
    errors: list[str] = []
    threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True).start()

    def watch() -> None:
        while process.poll() is None:
            if (should_cancel and should_cancel()) or time.monotonic() - started > timeout:
                process.kill()
                return
            time.sleep(0.5)
    threading.Thread(target=watch, daemon=True).start()
    for line in process.stdout:
        try:
            data = json.loads(line)
        except ValueError:
            continue
        if on_progress and "progress" in data:
            on_progress(float(data["progress"]), str(data.get("stage") or ""))
    process.wait()
    time.sleep(0.05)
    return process.returncode, (errors[0] if errors else "")[-600:]


def apply(src: Path, dst: Path, plan: list[dict], *, work: Path, on_progress=None, should_cancel=None, timeout: float = 3600) -> Path:
    """Lay the effects over ``src`` and write ``dst`` (audio untouched). Raises EffectsError with the reason when it cannot."""
    plan = clean_plan(plan)
    if not plan:
        raise EffectsError("هیچ افکتی برای اجرا نیست.")
    if not available():
        raise EffectsError("موتور افکت‌ها روی این سرور نصب نیست.")
    work.mkdir(parents=True, exist_ok=True)
    plan_file = work / "effects_plan.json"
    plan_file.write_text(json.dumps({"effects": plan}, ensure_ascii=False))
    code, error = _run(["--src", str(src), "--dst", str(dst), "--plan", str(plan_file), "--work", str(work)],
                       on_progress=on_progress, should_cancel=should_cancel, timeout=timeout)
    if should_cancel and should_cancel():
        raise EffectsError("افکت‌ها لغو شد.")
    if code != 0 or not dst.is_file() or dst.stat().st_size < 1000:
        raise EffectsError(f"اجرای افکت‌ها ناموفق بود (کد {code}). {error.strip()[-200:]}")
    return dst


def preview(src: Path, item: dict, t: float, png: Path, *, work: Path, timeout: float = 120) -> Path:
    """One frame of the video at ``t`` with the effect on it, to check text, timing and position quickly."""
    plan = clean_plan([item])
    if not available():
        raise EffectsError("موتور افکت‌ها روی این سرور نصب نیست.")
    work.mkdir(parents=True, exist_ok=True)
    plan_file = work / "effects_preview.json"
    plan_file.write_text(json.dumps({"effects": plan}, ensure_ascii=False))
    code, error = _run(["--src", str(src), "--plan", str(plan_file), "--work", str(work), "--still", f"{t:.3f}", "--png", str(png)],
                       on_progress=None, should_cancel=None, timeout=timeout)
    if code != 0 or not png.is_file():
        raise EffectsError(f"پیش‌نمایش افکت ساخته نشد (کد {code}). {error.strip()[-200:]}")
    return png

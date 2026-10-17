"""Turn extracted landing-page facts into an editable motion-reel board."""
from __future__ import annotations

import json
import re

from brain.ai_provider import get_provider
from engine.motion_recipes import BY_ID, select_recipe


SYSTEM = """You are a senior vertical product-video director. Return JSON only.
Use only facts present in SOURCE; never invent users, prices, metrics, reviews, or capabilities.
Build a concise 9:16 motion reel with 5-7 scenes and a strong narrative spine:
hook, problem/value, 2-3 pieces of evidence, payoff, CTA.
Every scene must contain: role, title, items (0-4 short strings), duration (2.2-5.0 seconds),
intent keywords, and why. Persian output unless the source is clearly English-only.
Keep titles under 8 words. Prefer product-specific nouns over generic marketing adjectives.
JSON shape: {"summary":"...","audience":"...","scenes":[...]}"""


def _fallback(source: dict) -> dict:
    name = source.get("name") or source.get("title") or "محصول"
    desc = source.get("description") or "راهی ساده‌تر برای انجام کار"
    features = list(source.get("features") or [])[:6]
    while len(features) < 3:
        features.append(desc)
    return {
        "summary": desc, "audience": "مخاطبان محصول",
        "scenes": [
            {"role": "hook", "title": name, "items": [], "duration": 3.0, "intent": ["hook", "brand"], "why": "معرفی فوری محصول"},
            {"role": "benefit", "title": features[0], "items": features[1:3], "duration": 4.0, "intent": ["benefit", "feature"], "why": "بیان ارزش اصلی"},
            {"role": "steps", "title": "چطور کار می‌کند؟", "items": features[:3], "duration": 4.5, "intent": ["steps", "process"], "why": "تبدیل ویژگی‌ها به مسیر قابل فهم"},
            {"role": "evidence", "title": features[2], "items": features[3:6], "duration": 4.0, "intent": ["feature", "proof"], "why": "نمایش جزئیات واقعی"},
            {"role": "cta", "title": "همین حالا ببین", "items": [source.get("host") or ""], "duration": 3.2, "intent": ["cta"], "why": "پایان روشن"},
        ],
    }


def plan(source: dict) -> tuple[dict, dict]:
    provider = get_provider()
    payload = json.dumps(source, ensure_ascii=False)
    try:
        result, usage = provider.generate_storyboard(payload, {
            "system_prompt": SYSTEM,
            "user_prompt": "SOURCE:\n" + payload,
        })
    except Exception:
        result, usage = _fallback(source), None
    if not isinstance(result, dict) or not isinstance(result.get("scenes"), list):
        result = _fallback(source)
    clean = []
    used: dict[str, int] = {}
    for index, raw in enumerate(result.get("scenes") or []):
        if not isinstance(raw, dict):
            continue
        title = " ".join(str(raw.get("title") or "").split())[:90]
        if not title:
            continue
        items = [" ".join(str(v).split())[:48] for v in raw.get("items") or [] if str(v).strip()][:4]
        role = str(raw.get("role") or ("hook" if not clean else "evidence"))[:24]
        requested = str(raw.get("recipe") or "")
        recipe = BY_ID.get(requested) or select_recipe(role=role, title=title, items=items, used=used)
        used[recipe.id] = used.get(recipe.id, 0) + 1
        try:
            duration = max(2.2, min(5.0, float(raw.get("duration") or 3.5)))
        except (TypeError, ValueError):
            duration = 3.5
        clean.append({
            "id": f"scene-{index + 1}", "role": role, "title": title, "items": items,
            "duration": round(duration, 2), "recipe": recipe.id, "renderer": recipe.renderer,
            "motion": recipe.motion, "why": str(raw.get("why") or recipe.best_for)[:180],
        })
    if len(clean) < 3:
        return plan_from_fallback(source, usage)
    return {"summary": str(result.get("summary") or source.get("description") or "")[:500],
            "audience": str(result.get("audience") or "")[:200], "scenes": clean[:8]}, _usage(usage)


def plan_from_fallback(source: dict, usage=None) -> tuple[dict, dict]:
    fallback = _fallback(source)
    scenes, used = [], {}
    for index, raw in enumerate(fallback["scenes"]):
        recipe = select_recipe(role=raw["role"], title=raw["title"], items=raw["items"], used=used)
        used[recipe.id] = used.get(recipe.id, 0) + 1
        scenes.append({"id": f"scene-{index + 1}", **raw, "recipe": recipe.id,
                       "renderer": recipe.renderer, "motion": recipe.motion})
    fallback["scenes"] = scenes
    return fallback, _usage(usage)


def _usage(usage) -> dict:
    if usage is None:
        return {}
    return {key: getattr(usage, key, None) for key in ("model", "input_tokens", "output_tokens", "elapsed_sec")}

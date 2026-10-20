#!/usr/bin/env python
"""Run the Creative Engine on a stored transcript and print what it decided (real model calls).

    JOBS_DIR=/tmp/eval-data python scripts/creative_eval.py path/to/transcript.json [request]

Use a copy of the gateway state as JOBS_DIR if you do not want new routes written to the live store.
This is the quality harness: read the concepts and the critique, judge them, then render.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import creative  # noqa: E402


def main() -> int:
    path = Path(sys.argv[1])
    request = " ".join(sys.argv[2:]) or "یه ریلز خیلی حرفه‌ای و جذاب ازش بساز"
    data = json.loads(path.read_text())
    sentences = data["sentences"] if isinstance(data, dict) else data
    print(f"{len(sentences)} sentences, {sentences[-1]['end']:.0f}s — request: {request}\n")
    for k, s in enumerate(sentences):
        print(f"  {k}: {s['text']}")
    started = time.monotonic()
    plan = creative.direct_talk(sentences, request)
    print(f"\n=== {plan.elapsed_s}s via {plan.models} (wall {time.monotonic() - started:.0f}s)\n")
    b = plan.brief
    print(f"BRIEF topic={b.topic}\n  core={b.core_message}\n  audience={b.audience} | goal={b.goal} | tone={b.tone}")
    print("  arc:", " → ".join(b.emotional_arc), "\n  proof:", b.proof_points, "\n  must_not:", b.must_not)
    for c in plan.concepts:
        mark = "★" if c.id == plan.chosen.id else " "
        print(f"\n{mark} [{c.id}] {c.name}  style={c.style_hint}\n   angle: {c.angle}\n   hook:  {c.hook}\n   look:  {c.visual_language} | pace: {c.pacing}")
        for beat in c.beats:
            print(f"   - {beat.role:7} s{beat.sentence}: {beat.visual}  [{beat.motion}]")
    for s in plan.critique.scores:
        print(f"\nscore {s.id}: hook={s.hook_strength} orig={s.originality} fit={s.fit_to_content} feas={s.feasibility} faith={s.faithfulness} → {s.total:.1f}  {s.note}")
    print(f"\nverdict: {plan.critique.verdict}\nimproved_hook: {plan.critique.improved_hook}\nimprovements: {plan.critique.improvements}")
    print(f"\nstyle chosen: {plan.style}\n\n--- director notes passed to the engine ---\n{plan.director_notes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

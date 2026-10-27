"""Project-local resource instances projected from the existing EditPlan.

No parallel timeline or storage: original segments/effects remain authoritative.
"""
import json


def edit_plan_instances(plan: dict) -> list[dict]:
    from engine.operations import segment_spans
    from engine.effects import canonical_effect
    from engine.effects_v4 import EXTENDED_EFFECTS
    spans = {span.id: span for span in segment_spans(plan)}
    instances = []
    for effect in plan.get("visual_effects", []):
        key, kind = effect["segment_id"], effect["type"]
        span = spans.get(key)
        if not span:
            continue
        legacy = kind if kind in EXTENDED_EFFECTS else canonical_effect(kind)
        instances.append({"id": "effect:" + key, "type": "effect", "resource_id": "editorgpt:" + legacy,
                          "segment_id": key, "start": span.start, "end": span.end,
                          "locked": bool(effect.get("locked")), "parameters_editable": False})
    for item in plan.get("transitions", []):
        pair = [item["from_segment_id"], item["to_segment_id"]]
        incoming = spans.get(pair[1])
        if incoming:
            instances.append({"id": "transition:" + json.dumps(pair, separators=(",", ":")),
                              "type": "transition", "resource_id": "editorgpt-transition:" + item["type"],
                              "from_segment_id": pair[0], "to_segment_id": pair[1],
                              "start": incoming.start,
                              "end": incoming.start + item.get("duration_frames", 0) / plan["canvas"]["fps"],
                              "locked": bool(item.get("locked")), "parameters_editable": True})
    return instances

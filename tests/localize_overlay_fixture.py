"""A deterministic Localize state and the ASS built from it (text measuring is replaced, so it needs no libass)."""
from engine import localize as media


def fake_boxes(texts, W, H, font, fonts_dir):
    return [(int(len(t) * s * 0.5), -int(s * 0.45), int(s * 0.35)) for t, s in texts]


def cover(start, end, cx, cy, w, h):
    box = {"cx": cx, "cy": cy, "w": w, "h": h}
    return {"start": start, "end": end, "box": box, "caps": True, "words": [], "frames": [{"box": box}]}


def state(detector="frame-outline-v6"):
    lines = [
        {"i": 0, "kind": "speech", "start": 1.0, "end": 4.0, "en": "HELLO THERE", "fa": "سلام به همه شما دوستان عزیز",
         "covers": [cover(1.0, 2.4, 0.5, 0.55, 0.5, 0.05), cover(2.4, 4.0, 0.5, 0.56, 0.4, 0.05)]},
        {"i": 1, "kind": "speech", "start": 4.5, "end": 7.0, "en": "NO CARD", "fa": "این یک جملهٔ بدون کارت است", "covers": []},
        {"i": 2, "kind": "cta", "start": 7.5, "end": 9.0, "en": "COMMENT", "fa": "عدد ۳۱ را کامنت کن",
         "covers": [cover(7.5, 9.0, 0.5, 0.6, 0.6, 0.06)]},
    ]
    return {"lines": lines, "title": "عنوان آزمایشی", "caption_box": "black", "title_box": "black", "caption_detector": detector,
            "cta_number": "31", "title_layout": None}


PLACEMENTS = [{"i": 0, "start": 1.0, "end": 4.0, "tempo": 1.0, "file": "a.wav"},
              {"i": 1, "start": 4.5, "end": 7.0, "tempo": 1.0, "file": "b.wav"},
              {"i": 2, "start": 7.5, "end": 9.0, "tempo": 1.0, "file": "c.wav"}]


def build(state_=None, **kwargs):
    original = media.measure_text_boxes
    media.measure_text_boxes = fake_boxes
    try:
        return media.plan_overlays(state_ or state(), PLACEMENTS, 1080, 1920, 12.0, source_duration=10.0, end_card_at=10.0, **kwargs)
    finally:
        media.measure_text_boxes = original

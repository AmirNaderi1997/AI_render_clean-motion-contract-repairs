import shutil
from pathlib import Path

from engine.hyperframes import product_reel


def test_word_times_spread_over_the_scene_by_word_length():
    timed = product_reel.word_times("این انگشتر انتخابته؟", 1.0, 4.0)
    assert [w for w, _ in timed] == ["این", "انگشتر", "انتخابته؟"]
    times = [t for _, t in timed]
    assert times[0] == 1.0 and times == sorted(times) and times[-1] < 4.0
    assert product_reel.word_times("", 0, 3) == []


def test_project_has_one_clip_per_scene_audio_tracks_and_a_registered_timeline(tmp_path, monkeypatch):
    gsap = tmp_path / "gsap.js"
    gsap.write_text("/* gsap */")
    monkeypatch.setattr("engine.hyperframes.assets.ensure_gsap", lambda *a, **k: gsap)
    photo = tmp_path / "p.png"
    photo.write_bytes(b"\x89PNG")
    voice = tmp_path / "v.mp3"
    voice.write_bytes(b"ID3")
    scenes = [{"asset": str(photo), "kind": "cutout", "accent": "#eb257b", "title": "دو انتخاب", "narration_text": "برای مراسم یا سالگرد",
               "narration": str(voice), "frames": 90, "visual_type": "kinetic_type"} for _ in range(3)]
    out = tmp_path / "project"
    product_reel.build_project(out, {"scenes": scenes, "music": None})
    html = (out / "index.html").read_text()
    assert html.count('class="clip scene"') == 3 and html.count("<audio") == 3
    assert 'data-duration="9"' in html and 'window.__timelines["reel"] = tl' in html
    assert 'id="s1" class="clip scene" data-start="2.7"' in html            # later scenes start one wipe early
    assert (out / "assets" / "p2.png").is_file() and (out / "assets" / "vo2.mp3").is_file()
    assert 'left:' not in "".join(l for l in html.splitlines() if l.lstrip().startswith("tl."))   # no layout-property tweens (engine lint)

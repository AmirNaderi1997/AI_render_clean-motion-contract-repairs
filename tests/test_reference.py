import shutil
import subprocess

import pytest

from creative import reference
from creative.schemas import CreativeUnavailable

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.fixture(scope="module")
def clip(tmp_path_factory):
    """1.0 s red, 2.0 s blue, 0.8 s green, 1.2 s white: four shots and three real cuts."""
    path = tmp_path_factory.mktemp("ref") / "ref.mp4"
    parts = [("red", 1.0), ("blue", 2.0), ("green", 0.8), ("white", 1.2)]
    inputs = sum([["-f", "lavfi", "-i", f"color=c={c}:s=360x640:d={d}:r=30"] for c, d in parts], [])
    graph = "".join(f"[{i}:v]" for i in range(4)) + "concat=n=4:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


def test_measured_facts_come_from_the_file(clip, tmp_path):
    seen = {}
    def fake_vision(sheet, profile):
        seen["sheet"] = sheet.is_file()
        return {"typography": "متن درشت سفید", "composition": "مرکزی", "overall_feel": "تند و ساده"}
    profile = reference.analyze(clip, tmp_path, describe=fake_vision)
    assert profile.usable and profile.shot_count == 4 and abs(profile.duration_s - 5.0) < 0.2
    assert [round(x) for x in profile.shot_lengths_s] == [1, 2, 1, 1]
    assert 0.5 < profile.cuts_per_second < 0.9 and profile.avg_shot_s == pytest.approx(1.25, abs=0.1)
    assert profile.typography == "متن درشت سفید" and seen["sheet"] and profile.frames_used >= 4
    assert profile.palette and profile.palette[0].startswith("#")
    assert "شنیده نشده" not in profile.sound and profile.sound == "بدون صدا."


def test_description_failure_keeps_measurements_and_says_so(clip, tmp_path):
    def broken(sheet, profile):
        raise RuntimeError("vision down")
    profile = reference.analyze(clip, tmp_path, describe=broken)
    assert profile.usable and profile.shot_count == 4 and profile.typography == ""
    assert "اندازه‌گیری" in profile.reason


def test_a_link_that_cannot_be_fetched_is_unavailable_with_a_reason_not_a_made_up_style(tmp_path):
    profile = reference.analyze("https://www.instagram.com/reel/abc123/", tmp_path)
    assert not profile.usable and profile.status == "unavailable" and "آپلود" in profile.reason
    assert profile.shot_count == 0 and not profile.typography
    with pytest.raises(CreativeUnavailable):
        reference.fetch("https://evil.example/video.mp4", tmp_path)


def test_missing_file_is_unavailable(tmp_path):
    assert reference.analyze(tmp_path / "nope.mp4", tmp_path).status == "unavailable"

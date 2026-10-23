import shutil
import subprocess

import pytest

from creative import fidelity, reference

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def make(path, parts, size="360x640"):
    inputs = sum([["-f", "lavfi", "-i", f"color=c={c}:s={size}:d={d}:r=30"] for c, d in parts], [])
    graph = "".join(f"[{i}:v]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path


@pytest.fixture(scope="module")
def fast_reference(tmp_path_factory):
    """Eight half-second shots in red/white: a fast, high-contrast reference."""
    folder = tmp_path_factory.mktemp("fid")
    video = make(folder / "ref.mp4", [("red", 0.5), ("white", 0.5)] * 4)
    return reference.analyze(video, folder, describe=lambda sheet, profile: {"typography": "درشت"}), folder


def test_a_slow_output_is_flagged_against_a_fast_reference(fast_reference, tmp_path):
    profile, _ = fast_reference
    assert profile.usable and profile.shot_count == 8 and profile.avg_shot_s == pytest.approx(0.5, abs=0.1)
    slow = make(tmp_path / "slow.mp4", [("blue", 4.0), ("green", 4.0)])
    result = fidelity.compare(slow, profile, judge=False)
    pacing = next(c for c in result["checks"] if c["aspect"] == "pacing")
    assert result["status"] == "needs_attention" and pacing["severity"] == "error" and not pacing["ok"]
    assert "نماها را بلندتر" not in pacing["suggestion"] and "کوتاه‌تر" in pacing["suggestion"]
    assert any(c["aspect"] == "palette" and not c["ok"] for c in result["checks"])


def test_a_matching_output_passes(fast_reference, tmp_path):
    profile, _ = fast_reference
    match = make(tmp_path / "match.mp4", [("red", 0.5), ("white", 0.5)] * 3)
    result = fidelity.compare(match, profile, judge=False)
    assert result["status"] == "passed" and all(c["ok"] for c in result["checks"])


def test_visual_findings_are_kept_only_with_evidence(fast_reference, tmp_path):
    profile, _ = fast_reference
    match = make(tmp_path / "m2.mp4", [("red", 0.5), ("white", 0.5)] * 3)
    judged = lambda measured, prof, work: {"findings": [{"aspect": "typography", "severity": "error", "evidence": "FRAME 2: متن کوچک و کم‌رنگ", "suggestion": "درشت‌تر"},
                                                        {"aspect": "feel", "severity": "error", "evidence": "", "suggestion": "x"}]}
    result = fidelity.compare(match, profile, judge=judged)
    assert result["status"] == "needs_attention" and len(result["findings"]) == 1


def test_no_profile_means_no_claim(tmp_path):
    result = fidelity.compare(tmp_path / "x.mp4", reference.unavailable("https://instagram.com/x", "r"))
    assert result["status"] == "unavailable"

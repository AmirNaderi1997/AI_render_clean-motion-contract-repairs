import shutil
import subprocess

import pytest

from creative import reference
from creative.schemas import CreativeUnavailable

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.fixture(autouse=True)
def _no_real_relay(monkeypatch):
    """A developer's .env may point at the real relay; unit tests must never use it unless they set their own."""
    monkeypatch.delenv("SOCIAL_RELAY_URL", raising=False)
    monkeypatch.delenv("SOCIAL_RELAY_SECRET", raising=False)


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
    profile = reference.analyze(clip, tmp_path, describe=fake_vision, describe_frames=lambda sheet: {})
    assert profile.usable and profile.shot_count == 4 and abs(profile.duration_s - 5.0) < 0.2
    assert [round(x) for x in profile.shot_lengths_s] == [1, 2, 1, 1]
    assert 0.5 < profile.cuts_per_second < 0.9 and profile.avg_shot_s == pytest.approx(1.25, abs=0.1)
    assert profile.typography == "متن درشت سفید" and seen["sheet"] and profile.frames_used >= 4
    assert profile.palette and profile.palette[0].startswith("#")
    assert "شنیده نشده" not in profile.sound and profile.sound == "بدون صدا."


def test_description_failure_keeps_measurements_and_says_so(clip, tmp_path):
    def broken(sheet, profile):
        raise RuntimeError("vision down")
    profile = reference.analyze(clip, tmp_path, describe=broken, describe_frames=lambda sheet: {})
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


def test_frame_review_keeps_every_cut_and_describes_each_frame(clip, tmp_path):
    cuts = reference.cut_times(clip, 5.0)
    plan = reference.table_frames(cuts, 5.0)
    shots = {shot for _, shot in plan}
    assert shots == {1, 2, 3, 4} and len(plan) <= reference.MAX_TABLE_FRAMES
    assert plan == sorted(plan) and all(0 <= t <= 5.0 for t, _ in plan)

    def fake_frames(sheet):
        assert sheet.is_file()
        return {"frames": [{"index": i, "on_screen_text": f"متن {i}", "composition": "مرکزی", "change": "برش"} for i in range(40)]}

    profile = reference.analyze(clip, tmp_path, describe=lambda s, p: {}, describe_frames=fake_frames, table_dir=tmp_path / "out")
    assert profile.frame_table and all(row["described"] for row in profile.frame_table)
    assert profile.frame_table[0]["text"].startswith("متن: «متن 0»") and {r["shot"] for r in profile.frame_table} == {1, 2, 3, 4}
    image = tmp_path / "out" / "frame-table.jpg"
    assert image.is_file() and image.stat().st_size > 5000


def test_failed_frame_descriptions_are_marked_not_invented(clip, tmp_path):
    def broken(sheet):
        raise RuntimeError("vision down")
    profile = reference.analyze(clip, tmp_path, describe=lambda s, p: {}, describe_frames=broken)
    assert profile.frame_table and not any(row["described"] for row in profile.frame_table) and all(row["text"] == "" for row in profile.frame_table)


def test_long_shots_get_regular_frames_but_the_total_is_capped():
    plan = reference.table_frames([20.0], 40.0)
    assert len(plan) == reference.MAX_TABLE_FRAMES and {s for _, s in plan} == {1, 2} and plan[0][0] < 0.2


def test_download_failures_are_explained_honestly():
    assert "دسترسی ندارد" in reference.download_failure_reason("Connection refused")
    assert "ورود به حساب" in reference.download_failure_reason("Instagram: login required")
    assert "حد مجاز" in reference.download_failure_reason("File is larger than max-filesize")
    assert "آپلود" in reference.download_failure_reason("something unknown")


def test_direct_download_plumbing_with_yt_dlp(clip, tmp_path, monkeypatch):
    """The downloader is wired correctly: size/duration filters, output name, proxy option. A local server stands in for the social site."""
    pytest.importorskip("yt_dlp")
    import functools, http.server, threading
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(clip.parent))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(reference, "HOSTS", {"127.0.0.1"})
    monkeypatch.delenv("SOCIAL_RELAY_URL", raising=False)      # this test is about the local downloader, not the relay
    monkeypatch.delenv("SOCIAL_RELAY_SECRET", raising=False)
    try:
        path = reference.fetch(f"http://127.0.0.1:{server.server_port}/{clip.name}", tmp_path / "dl")
    finally:
        server.shutdown()
    assert path.name.startswith("reference.") and path.stat().st_size > 1000


def test_relay_download_and_its_failures(clip, tmp_path, monkeypatch):
    """The app talks to the Vercel relay (a local server plays its part): file streamed back, secret sent, refusals explained."""
    import http.server, json, threading
    seen = {}

    class Relay(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            seen["secret"], seen["url"] = self.headers.get("x-relay-secret"), body["url"]
            if "private" in body["url"]:
                payload = json.dumps({"error": "download_failed", "message": "ERROR: Instagram sent an empty media response. logged-in"}).encode()
                self.send_response(502); self.send_header("content-type", "application/json")
            else:
                payload = clip.read_bytes()
                self.send_response(200); self.send_header("content-type", "video/mp4"); self.send_header("x-source-ext", "mp4")
            self.send_header("content-length", str(len(payload))); self.end_headers(); self.wfile.write(payload)

        def log_message(self, *a):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("SOCIAL_RELAY_URL", f"http://127.0.0.1:{server.server_port}/api/index")
    monkeypatch.setenv("SOCIAL_RELAY_SECRET", "s" * 40)
    try:
        assert reference.relay_configured()
        profile = reference.analyze("https://www.tiktok.com/@a/video/1", tmp_path / "a", describe=lambda s, p: {}, describe_frames=lambda s: {})
        assert profile.usable and profile.shot_count == 4 and profile.source.startswith("https://www.tiktok.com")
        assert seen["secret"] == "s" * 40 and seen["url"].endswith("/video/1")
        refused = reference.analyze("https://www.instagram.com/reel/private123/", tmp_path / "b")
        assert refused.status == "unavailable" and "ورود به حساب" in refused.reason
    finally:
        server.shutdown()
    monkeypatch.setenv("SOCIAL_RELAY_URL", "http://127.0.0.1:9/api/index")
    down = reference.analyze("https://www.tiktok.com/@a/video/2", tmp_path / "c")
    assert down.status == "unavailable" and "رلی" in down.reason


def test_rate_limited_vision_waits_out_the_stated_cooldown_once(monkeypatch):
    waits, calls = [], []
    monkeypatch.setattr(reference, "_sleep", waits.append)
    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("LM API HTTP 429: All models exhausted ... Soonest reset ~88s.")
        return "ok"
    assert reference._with_cooldown(flaky) == "ok" and waits == [90]
    def hopeless():
        raise RuntimeError("HTTP 429 Soonest reset ~900s")
    with pytest.raises(RuntimeError):
        reference._with_cooldown(hopeless)
    assert waits == [90]


def test_sheets_the_provider_failed_are_retried_once(clip, tmp_path):
    calls = {}
    def flaky(sheet):
        calls[sheet.name] = calls.get(sheet.name, 0) + 1
        if calls[sheet.name] == 1:
            raise RuntimeError("502 upstream")
        return {"frames": [{"index": i, "on_screen_text": "", "composition": "ok", "change": ""} for i in range(40)]}
    profile = reference.analyze(clip, tmp_path, describe=lambda s, p: {}, describe_frames=flaky)
    assert profile.frame_table and all(row["described"] for row in profile.frame_table) and all(n == 2 for n in calls.values())

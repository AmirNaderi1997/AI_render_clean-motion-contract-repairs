from pathlib import Path

import pytest
from PIL import Image

from app import studio_url
from brain.product_assets import inspect_assets
from brain import qc_pipeline
from brain.qc_review import QCIssue
from engine.remotion_renderer import render


def test_product_gallery_excludes_site_social_preview(tmp_path, monkeypatch):
    import io
    image = io.BytesIO()
    Image.new("RGB", (500, 500), "white").save(image, format="PNG")
    requested = []
    def fetch(url, **kwargs):
        requested.append(url)
        if url.endswith("/product"):
            return (b'<h1>Tool kit</h1><meta property="og:image" content="/homepage.png">'
                    b'<script type="application/ld+json">{"@type":"Product","name":"Tool kit","image":"/kit.png"}</script>', url, "text/html")
        return image.getvalue(), url, "image/png"
    monkeypatch.setattr(studio_url, "_fetch", fetch)
    result = studio_url.inspect_page("https://example.com/product", tmp_path)
    assert len(result["images"]) == 1
    assert result["images"][0]["role"] == "product"
    assert "https://example.com/homepage.png" not in requested


def test_visual_catalog_rejects_unrelated_screenshot(tmp_path, monkeypatch):
    images = [tmp_path / "home.jpg", tmp_path / "kit.jpg"]
    for path in images:
        Image.new("RGB", (500, 500)).save(path)
    monkeypatch.setattr("brain.llm.chat_vision", lambda *args, **kwargs: ({"assets": [
        {"index": 0, "usable": False, "subject": "homepage"},
        {"index": 1, "usable": True, "subject": "tool kit"},
    ]}, None))
    catalog = inspect_assets(images, "tool kit")
    assert [row["index"] for row in catalog] == [1]


def test_remotion_rejects_asset_outside_job_before_spawning(tmp_path):
    root = tmp_path / "job"
    root.mkdir()
    outside = tmp_path / "private.jpg"
    outside.write_bytes(b"private")
    with pytest.raises(ValueError, match="Invalid owned"):
        render({"scenes": [{"asset": "../private.jpg", "frames": 30}]}, root / "out.mp4", job_dir=root)


def test_qc_does_not_approve_unfixable_framing_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(qc_pipeline, "validate_plan", lambda *args, **kwargs: (object(), []))
    monkeypatch.setattr(qc_pipeline, "sample_keyframes", lambda *args: [])
    monkeypatch.setattr(qc_pipeline, "sample_audio_clips", lambda *args: [])
    monkeypatch.setattr(qc_pipeline, "deterministic_checks", lambda *args: [
        QCIssue("s1", 1, "bad_framing", "error", "Product cropped", "reframe")])
    monkeypatch.setattr(qc_pipeline, "patch_plan", lambda plan, *args, **kwargs: (plan, []))
    result = qc_pipeline.run_qc(tmp_path, tmp_path / "out.mp4", {}, skip_vision=True)
    assert result.status == "needs_review"
    assert result.total_issues == 1


def test_remotion_cannot_read_arbitrary_server_file_as_music(tmp_path):
    root = tmp_path / "job"
    root.mkdir()
    (root / "image.jpg").write_bytes(b"owned")
    private = tmp_path / "private.env"
    private.write_bytes(b"private")
    with pytest.raises(ValueError, match="Music must belong"):
        render({"scenes": [{"asset": "image.jpg", "frames": 30}], "music": str(private)},
               root / "out.mp4", job_dir=root)

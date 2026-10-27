import cv2
import numpy as np

from engine import remotion_prep


def _photo(tmp_path, backdrop):
    image = np.full((400, 400, 3), backdrop, np.uint8)
    cv2.circle(image, (200, 200), 110, (40, 30, 200), -1)                 # a red stone
    cv2.circle(image, (200, 200), 150, (250, 250, 250), 14)               # a white halo ring touching nothing else
    path = tmp_path / "p.png"
    cv2.imwrite(str(path), image)
    return path


def test_white_studio_photo_becomes_a_cutout_with_the_product_accent(tmp_path):
    result = remotion_prep.prepare(_photo(tmp_path, (255, 255, 255)), tmp_path / "out")
    assert result["kind"] == "cutout" and result["asset"].endswith("-cutout.png")
    rgba = cv2.imread(result["asset"], cv2.IMREAD_UNCHANGED)
    assert rgba.shape[2] == 4 and rgba[5, 5, 3] == 0 and rgba[200, 200, 3] == 255      # corner transparent, stone opaque
    assert result["accent"].startswith("#") and result["accent"][1:3] > result["accent"][5:7]    # red-ish, not the backdrop


def test_dark_photo_stays_a_photo(tmp_path):
    result = remotion_prep.prepare(_photo(tmp_path, (90, 40, 10)), tmp_path / "out")
    assert result["kind"] == "photo" and result["asset"].endswith("p.png")


def test_unreadable_file_falls_back_to_itself(tmp_path):
    bad = tmp_path / "x.webp"
    bad.write_bytes(b"")
    assert remotion_prep.prepare(bad, tmp_path / "out")["kind"] == "photo"

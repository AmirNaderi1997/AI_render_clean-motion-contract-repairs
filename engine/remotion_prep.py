"""Prepare owned product photos for the directed Remotion reel: cut a studio-white background away and find the accent colour.

Deterministic image processing only (OpenCV): no model call, no cost.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

NEAR_WHITE = 226          # min(B,G,R) above this on the border region counts as studio backdrop
DEFAULT_ACCENT = "#d9b36c"


def _read(path: Path) -> np.ndarray | None:
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _backdrop_mask(image: np.ndarray) -> np.ndarray:
    """Pixels that are near-white AND connected to the picture border: the studio backdrop and its soft shadow edge, not the white stones inside."""
    near = (image.min(axis=2) >= NEAR_WHITE).astype(np.uint8)
    count, labels = cv2.connectedComponents(near, connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    border = border[border != 0]
    return np.isin(labels, border)


def is_white_studio(image: np.ndarray) -> bool:
    edge = np.concatenate([image[:6].reshape(-1, 3), image[-6:].reshape(-1, 3), image[:, :6].reshape(-1, 3), image[:, -6:].reshape(-1, 3)])
    return bool(edge.min(axis=1).mean() > 232 and edge.std() < 14)


def accent_of(image: np.ndarray, ignore: np.ndarray | None = None) -> str:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    keep = (hsv[..., 1] > 110) & (hsv[..., 2] > 70)
    if ignore is not None:
        keep &= ~ignore
    if keep.sum() < 200:
        return DEFAULT_ACCENT
    hue = np.median(hsv[..., 0][keep])
    sat = max(160, float(np.median(hsv[..., 1][keep])))
    colour = cv2.cvtColor(np.uint8([[[hue, min(255, sat), 235]]]), cv2.COLOR_HSV2BGR)[0, 0]
    return "#{:02x}{:02x}{:02x}".format(int(colour[2]), int(colour[1]), int(colour[0]))


def prepare(path: str | Path, out_dir: Path) -> dict:
    """{asset: file to show, kind: 'cutout' (transparent product) | 'photo' (rectangular picture), accent: '#rrggbb'}."""
    path = Path(path)
    image = _read(path)
    if image is None:
        return {"asset": str(path), "kind": "photo", "accent": DEFAULT_ACCENT}
    if not is_white_studio(image):
        return {"asset": str(path), "kind": "photo", "accent": accent_of(image)}
    backdrop = _backdrop_mask(image)
    if backdrop.mean() > 0.92 or backdrop.mean() < 0.15:       # nothing to separate, or it would eat the product
        return {"asset": str(path), "kind": "photo", "accent": accent_of(image)}
    alpha = np.where(backdrop, 0, 255).astype(np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    # White stones are as bright as the backdrop: whatever lies inside the product's outline belongs to the product.
    closed = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        biggest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(biggest) > 0.04 * alpha.size:
            filled = np.zeros_like(alpha)
            cv2.drawContours(filled, [biggest], -1, 255, thickness=cv2.FILLED)
            alpha = np.maximum(alpha, filled)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.6)
    # Pull the cut edge inwards a little so no white fringe survives.
    alpha = cv2.erode(alpha, np.ones((3, 3), np.uint8))
    rgba = np.dstack([image, alpha])
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    out = out_dir / f"{path.stem}-{digest}-cutout.png"
    if not out.is_file():
        cv2.imwrite(str(out), rgba)
    return {"asset": str(out), "kind": "cutout", "accent": accent_of(image, backdrop)}

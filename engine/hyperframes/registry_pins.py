"""Immutable, bounded source installer for the two existing registry adapters.

No agent-controlled URL, path, command, dependencies or manifest execution.
The upstream code license does not approve fonts, runtimes or user assets.
"""
import hashlib
import json
from pathlib import Path

COMMIT = "07b0f2cda1cf7b51e0f12d0d05c304b37b4e881c"
BASE = f"https://raw.githubusercontent.com/heygen-com/hyperframes/{COMMIT}"
PINS = {
    "caption-kinetic-slam": "86b7a54e045f626d1375636a2f1cde19c2f3cbdad1df1d7d0204fe6b4452044a",
    "paper-collage-reveal": "e7d138d73785cda61179b1c821d3b2590f90e61b8ac9e22e3bccb245eec9fafa",
}
LICENSE_SHA256 = "4259155fb06f127687ee7b0a8a3682d45132db0f2da26cbc0b7a2d1e796436b8"
MAX_BYTES = 512_000


def _fetch(url: str) -> bytes:
    import httpx
    chunks = []
    size = 0
    with httpx.stream("GET", url, timeout=30, follow_redirects=False) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("Pinned resource exceeds size limit")
            chunks.append(chunk)
    return b"".join(chunks)


def _verified(data: bytes, expected: str) -> bytes:
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Pinned resource integrity mismatch")
    return data


def install_pinned(project_dir: Path, name: str) -> bool:
    if name not in PINS:
        return False
    source_url = f"{BASE}/registry/components/{name}/{name}.html"
    source = _verified(_fetch(source_url), PINS[name])
    license_text = _verified(_fetch(f"{BASE}/LICENSE"), LICENSE_SHA256)
    root = project_dir.resolve()
    target = root / "compositions" / "components" / f"{name}.html"
    receipts = root / "resource-receipts"
    for path in (target, receipts / f"{name}.json", receipts / "hyperframes-LICENSE.txt"):
        if not path.resolve().is_relative_to(root):
            raise ValueError("Resource output escapes project")
    target.parent.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source)
    (receipts / "hyperframes-LICENSE.txt").write_bytes(license_text)
    (receipts / f"{name}.json").write_text(json.dumps({
        "resource_id": f"hyperframes:{name}", "upstream_commit": COMMIT,
        "source_url": source_url, "source_sha256": PINS[name],
        "code_license": "Apache-2.0", "license_sha256": LICENSE_SHA256,
        "modified_by": "EditorGPT context-specific adapter",
        "dependencies_approved": False, "commercial_use_approved": False,
    }, indent=2))
    return True

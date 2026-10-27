"""Reviewed local snapshot fingerprints; not upstream code/license receipts.

Paths are a fixed allowlist, never supplied by an agent or HTTP client. Large
files are hashed in chunks. A mismatch is visible, not silently re-approved.
"""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = {
    "engine/hyperframes/catalog_index.json": "33deb3c708b44d10b8c2237a1264fcfea037c982f2838b1c3b86619c119ac6d5",
    "engine/hyperframes/catalog_profiles.json": "5225b23157585fadf0b6b02f3e11667f2e70b5318b857d967e273c9d27dd6cce",
    "engine/hyperframes/registry_runtime.py": "21d8c4d3dd0aa7e4e8a0013ea1c700a1d6fb95cf4200f4843b4aedc2c30325ae",
    "engine/effects_v4.py": "88f6d6be1d3e86793c16c8aa28f6e3ccaa2d5bab583751a0315cc063d9e363b2",
    "engine/motion_recipes.py": "b0601098e79a43bbd53e330b129ef4927b588832e3bf33110120ca68cefe8031",
    "engine/schema.py": "5375e6441e207efc608ab72dbfbd638cfe2dff8cdf1bbfb4dc1fd0f16d9c4caf",
}


def snapshot_integrity() -> dict:
    files = []
    for relative, expected in SNAPSHOT.items():
        path = ROOT / relative
        actual = None
        try:
            # Reject symlink escapes even for a trusted, fixed relative path.
            path.resolve().relative_to(ROOT.resolve())
            with path.open("rb") as source:
                digest = hashlib.sha256()
                for chunk in iter(lambda: source.read(65536), b""):
                    digest.update(chunk)
                actual = digest.hexdigest()
        except (OSError, ValueError):
            pass
        files.append({"path": relative, "expected_sha256": expected,
                      "actual_sha256": actual, "matches": actual == expected})
    return {"scope": "local-metadata-and-adapters", "verified": all(f["matches"] for f in files),
            "upstream_install_pinned": False, "license_approved": False, "files": files}

"""Install the reviewed, pinned upstream pack through Hermes' native Skills Hub.

Run with the official Hermes managed Python. No network, models or shell tools
are used. Existing installations are never overwritten automatically.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

REVISION = "d03c56bb598be770c60b201f94237e5d1a4268a6"
REPOSITORY = "https://github.com/Jakeschincariol/instagram-agent-skill"
SKILLS = (
    "ig-reel", "ig-viral", "ig-caption", "ig-carousel", "ig-story",
    "ig-profile", "ig-plan", "ig-human", "ig-comment", "ig-reply",
    "ig-dm", "ig-repurpose", "ig-audit",
)


def git(source: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(source), *args], timeout=15)


def bundles(source: Path):
    """Read committed objects, never potentially modified checkout files."""
    actual = git(source, "rev-parse", "HEAD").decode().strip()
    if actual != REVISION:
        raise ValueError(f"Expected reviewed revision {REVISION}; got {actual}")
    license_text = git(source, "show", f"{REVISION}:LICENSE")
    voice = git(source, "show", f"{REVISION}:templates/voice.md")
    result = {}
    for name in SKILLS:
        prefix = f"skills/{name}/"
        listing = git(source, "ls-tree", "-r", REVISION, "--", prefix).decode().splitlines()
        files = {"LICENSE": license_text, "references/voice-template.md": voice}
        for entry in listing:
            metadata, path = entry.split("\t", 1)
            if not metadata.startswith(("100644 blob ", "100755 blob ")):
                raise ValueError(f"Unsupported upstream file mode: {path}")
            files[path[len(prefix):]] = git(source, "show", f"{REVISION}:{path}")
        if "SKILL.md" not in files:
            raise ValueError(f"Missing definition: {name}")
        result[name] = files
    return result


def install(source: Path, runtime: Path, home: Path):
    pack = bundles(source)  # Validate every input before changing the profile.
    os.environ["HERMES_HOME"] = str(home.resolve())
    sys.path.insert(0, str(runtime.resolve()))
    import hermes_bootstrap  # noqa: F401 — official environment initialization
    from tools.skills_guard import scan_skill, should_allow_install
    from tools.skills_hub import HubLockFile
    from tools.skills_hub_install import install_from_quarantine, quarantine_bundle
    from tools.skills_hub_models import SkillBundle

    for name, files in pack.items():
        existing = HubLockFile().get_installed(name)
        if existing:
            if existing.get("metadata", {}).get("revision") != REVISION:
                raise ValueError(f"{name} already exists at another revision; review before upgrading")
            print(f"Already installed: {name}")
            continue
        target = home / "skills" / name
        if target.exists() or target.is_symlink():
            raise ValueError(f"Refusing to replace existing skill: {name}")
        bundle = SkillBundle(
            name=name, files=files, source="github", trust_level="community",
            identifier=f"Jakeschincariol/instagram-agent-skill/skills/{name}",
            metadata={"revision": REVISION, "repository": REPOSITORY,
                      "license": "MIT", "author": "Jake Schincariol"},
        )
        quarantine = quarantine_bundle(bundle)
        scan = scan_skill(quarantine, source=bundle.identifier)
        allowed, reason = should_allow_install(scan, force=False)
        if not allowed:
            raise ValueError(f"Security scan refused {name}: {reason}")
        install_from_quarantine(quarantine, name, "", bundle, scan)
        print(f"Installed: {name} ({scan.verdict})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True)
    args = parser.parse_args()
    install(args.source, args.runtime, args.home)

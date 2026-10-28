"""Offline installer contract; integration discovery is verified with native CLI."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

spec = spec_from_file_location("instagram_install", Path(__file__).parents[1] / "scripts/install_instagram_skills.py")
installer = module_from_spec(spec)
spec.loader.exec_module(installer)


def test_exact_thirteen_unique_skills():
    assert len(installer.SKILLS) == len(set(installer.SKILLS)) == 13
    assert all(name.startswith("ig-") for name in installer.SKILLS)


def test_wrong_revision_rejected_before_files_are_read(monkeypatch):
    calls = []

    def fake_git(source, *args):
        calls.append(args)
        return b"unreviewed-revision\n"

    monkeypatch.setattr(installer, "git", fake_git)
    with pytest.raises(ValueError, match="Expected reviewed revision"):
        installer.bundles(Path("unused"))
    assert calls == [("rev-parse", "HEAD")]


def test_symlink_from_upstream_rejected(monkeypatch):
    def fake_git(source, *args):
        if args[0] == "rev-parse":
            return installer.REVISION.encode()
        if args[0] == "ls-tree":
            return b"120000 blob abc\tskills/ig-reel/SKILL.md\n"
        return b"MIT example"

    monkeypatch.setattr(installer, "git", fake_git)
    with pytest.raises(ValueError, match="Unsupported upstream file mode"):
        installer.bundles(Path("unused"))

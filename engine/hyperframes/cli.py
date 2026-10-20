"""Resolve the pinned CLI without requiring an online npx install per job."""
import os
import shutil
from pathlib import Path

VERSION = "0.8.161"


def cli_command() -> list[str]:
    node = shutil.which("node")
    candidates = [Path(os.environ.get("HYPERFRAMES_CLI", "/opt/hyperframes/node_modules/hyperframes/bin/hyperframes.mjs")),
                  Path.home() / ".cache/editor-hyperframes/node_modules/hyperframes/bin/hyperframes.mjs"]
    for path in candidates:
        if node and path.is_file():
            return [node, str(path)]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--yes", f"hyperframes@{VERSION}"]
    raise RuntimeError("HyperFrames runtime is not installed: the server needs its pinned CLI and Node 22 (npm/npx is also missing). The existing rough cut has been preserved.")

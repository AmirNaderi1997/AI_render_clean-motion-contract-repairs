"""Import a user-provided RTF key into the ignored, private local runtime file.

Never prints file content or credentials; does not make external requests.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def main():
    target = Path(__file__).resolve().parents[1] / ".local-hermes-test/runtime.json"
    result = subprocess.run(["/usr/bin/textutil", "-convert", "txt", "-stdout", sys.argv[1]],
                            capture_output=True, check=False)
    if result.returncode:
        raise SystemExit("Could not read the supplied RTF file.")
    content = result.stdout.decode("utf-8").strip()
    candidates = re.findall(r"\b(?:ak_|comp_)[A-Za-z0-9_-]{16,}\b", content)
    if not candidates and re.fullmatch(r"[A-Za-z0-9_-]{24,256}", content):
        candidates = [content]
    if len(set(candidates)) != 1:
        raise SystemExit("Expected exactly one API key; no settings changed.")
    state = json.loads(target.read_text())
    state["composio_api_key"] = candidates[0]
    temporary = target.with_suffix(".new")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as handle:
        json.dump(state, handle)
    os.replace(temporary, target)
    os.chmod(target, 0o600)
    print("Local key imported; value is not displayed.")


if __name__ == "__main__":
    main()

"""Isolated loopback-only integration preview; never loads the old app's .env.

Run with an EditorGPT Python environment. Frontend dependencies must be installed.
No existing jobs, accounts, databases or provider settings are overwritten.
"""
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".local-hermes-test"


def main():
    DATA.mkdir(mode=0o700, exist_ok=True)
    state_file = DATA / "runtime.json"
    if not state_file.exists():
        descriptor = os.open(state_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump({"jwt": secrets.token_hex(32), "encryption": secrets.token_hex(32),
                       "instance": "local-test-" + secrets.token_hex(16)}, handle)
    state = json.loads(state_file.read_text())
    env = dict(os.environ)
    if state.get("composio_api_key"):
        env["COMPOSIO_API_KEY"] = state["composio_api_key"]
    packages = DATA / "python-packages"
    if packages.exists():
        env["PYTHONPATH"] = str(packages) + os.pathsep + env.get("PYTHONPATH", "")
    env.update(APP_ENV="development", ENV="development", ENVIRONMENT="development",
        DATABASE_URL="", REDIS_URL="", JWT_SECRET=state["jwt"],
        HERMES_TOKEN_KEY=state["encryption"], HERMES_ENCRYPTION_KEY=state["encryption"],
        JOBS_DIR=str(DATA / "jobs"), HERMES_DATA_DIR=str(DATA / "hermes"),
        COMPOSIO_INSTANCE_ID=state["instance"], COMPOSIO_READ_TOOLS="",
        COMPOSIO_CALLBACK_URL="http://127.0.0.1:5187/hermes/settings",
        VITE_REQUIRE_LOCAL_AUTH="1",
        API_TARGET="http://127.0.0.1:8192", HERMES_TARGET="http://127.0.0.1:8193")
    # No optional LAN/TLS settings leak into this loopback-only preview.
    for key in ("EDITOR_DEV_CERT", "EDITOR_DEV_KEY", "EDITOR_LAN_HOST", "EDITOR_LAN_CA", "EDITOR_LAN_TLS_PORT"):
        env.pop(key, None)
    commands = [
        ([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8192"], ROOT),
        ([sys.executable, "-m", "uvicorn", "hermes.main:app", "--host", "127.0.0.1", "--port", "8193"], ROOT),
        ([str(ROOT / "web/node_modules/.bin/vite"), "--host", "127.0.0.1", "--port", "5187"], ROOT / "web"),
    ]
    children = []
    def stop(*_):
        for child in children:
            if child.poll() is None:
                child.terminate()
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for command, directory in commands:
            children.append(subprocess.Popen(command, cwd=directory, env=env))
        print("Hermes integration preview: http://127.0.0.1:5187/hermes/settings", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()


if __name__ == "__main__":
    main()

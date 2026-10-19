"""Attach a reviewed scene configuration to a local job and start its real render.

Uses the existing plan/version/render APIs, so previous exports stay available.
"""
import argparse
import json
import shutil
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("job_dir", type=Path)
parser.add_argument("config", type=Path)
parser.add_argument("--api", default="http://127.0.0.1:8000")
args = parser.parse_args()
root = args.job_dir.resolve()
config = json.loads(args.config.read_text())
for scene in config["scenes"]:
    for key in ("asset", "narration"):
        if scene.get(key):
            scene[key] = str(Path(scene[key]).resolve().relative_to(root))
    scene["supporting_assets"] = [str(Path(item).resolve().relative_to(root)) for item in scene.get("supporting_assets", [])]
music = root / "generated/motion_music.mp3"
if not music.exists():
    source = Path(__file__).resolve().parents[1] / "assets/music/cinematic_pulse.mp3"
    shutil.copy2(source, music)
config["music"] = str(music.relative_to(root))

with urllib.request.urlopen(f"{args.api}/jobs/{root.name}/plan.json", timeout=20) as response:
    plan = json.load(response)
plan.setdefault("generation_meta", {}).update(renderer="remotion", remotion=config)
plan["generation_meta"]["warnings"] = []
payload = json.dumps({"plan": plan}).encode()
request = urllib.request.Request(f"{args.api}/jobs/{root.name}/plan", data=payload,
                                 headers={"Content-Type": "application/json"}, method="PUT")
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.read().decode())
request = urllib.request.Request(f"{args.api}/jobs/{root.name}/render", data=b"", method="POST")
with urllib.request.urlopen(request, timeout=30) as response:
    print(response.read().decode())

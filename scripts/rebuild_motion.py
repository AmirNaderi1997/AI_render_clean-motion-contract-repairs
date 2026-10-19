"""Re-render an existing storyboard using owned product photos and cached voice.

Writes a new file. Never overwrites the existing published export.
"""
import argparse
import json
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.remotion_renderer import render

parser = argparse.ArgumentParser()
parser.add_argument("job_dir", type=Path)
parser.add_argument("output", type=Path)
parser.add_argument("--exclude-source", action="append", default=[])
parser.add_argument("--review-assets", action="store_true")
args = parser.parse_args()
job_dir = args.job_dir.resolve()
storyboard = json.loads((job_dir / "storyboard.json").read_text())
checkpoint = json.loads((job_dir / "generated/generation_checkpoint.json").read_text())
assets = sorted(path for path in (job_dir / "generated/source_assets").iterdir()
                if path.name not in args.exclude_source)
if not assets:
    raise ValueError("No owned product assets remain")
voices = {item["scene_index"]: item for item in checkpoint.get("narration", [])}
assignments = {}
if args.review_assets:
    from brain.product_assets import inspect_assets
    from brain.llm import chat_json
    catalog = inspect_assets(assets, storyboard["prompt"])
    result, _usage = chat_json(
        "Match product photos to video scenes. Return JSON {assignments:[{scene_index:0,asset_index:1}]}. "
        "Use only supplied asset indices. Pick the complete product for hook and final CTA. "
        "Choose a photo actually illustrating each caption; reject unrelated or misleading matches.",
        json.dumps({"assets": [{k:v for k,v in row.items() if k != "path"} for row in catalog],
                    "scenes": storyboard["scenes"]}, ensure_ascii=False), max_tokens=1200,
    )
    assignments = {row["scene_index"]: row["asset_index"] for row in result.get("assignments", [])
                   if type(row.get("asset_index")) is int and row["asset_index"] in {item["index"] for item in catalog}}
scenes = []
for index, scene in enumerate(storyboard["scenes"]):
    voice = voices.get(scene["index"])
    asset_index = assignments.get(scene["index"], index % len(assets))
    scenes.append({"asset": str(assets[asset_index].relative_to(job_dir)),
                   "title": scene["text_overlay"], "frames": round(scene["duration_s"] * 30),
                   "supporting_assets": [str(asset.relative_to(job_dir)) for asset in assets[:3]],
                   "narration": str(Path(voice["file_path"]).relative_to(job_dir)) if voice else None})
music = (checkpoint.get("music") or {}).get("file_path")
if not music:
    from engine.library import scan_category
    from engine.schema import PROJECT_ROOT
    candidates = scan_category("music")
    if candidates:
        source = PROJECT_ROOT / candidates[0].path
        target = job_dir / "generated" / ("motion_music" + source.suffix)
        shutil.copy2(source, target)
        music = str(target)
config = {"scenes": scenes, "music": music}
render(config, args.output.resolve(), job_dir=job_dir)
print(args.output.resolve())

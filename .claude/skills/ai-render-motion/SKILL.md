---
name: ai-render-motion
description: Maintain AI Render product-reel and talking_2 motion templates, caption alignment, export gates and their evidence. Read before changing engine/hyperframes, engine/remotion_renderer.py or remotion compositions.
---

# Project motion rules

A skill document is not proof a feature works. Read the implementation on the
current branch and keep direct tests, fixture renders, app runs and human review
distinct. Local-only commits and old benchmark media are comparison material,
not acceptance for the current checkout.

## Data and templates

Models produce validated data only. Maintained templates produce all HTML,
CSS, GSAP and React. Never accept authored HTML/CSS/JS/JSX from model output,
remote pages, chat or uploaded content. No eval, dynamically compiled model code,
remote scripts, iframe execution or dangerouslySetInnerHTML. Engineers may edit
the maintained templates; a user-facing code-authoring route must not be added.
Escape HyperFrames strings and render React strings as text. The chat motion
graphic is disabled (`app/motion_graphic.py`, `creative/motion_graphic.py`). Do
not re-enable its legacy code-authoring workers.

`engine/motion_contract.py` owns product limits and owned-path admission:
1–30 scenes, 1–900 integer frames per scene, at most 2700 frames total and
at most three supporting assets. Both engines validate before preparation and
rendering. Media belongs to the current job; music may use the approved library.
Do not duplicate or relax those limits in a new adapter.

## Product reel and speech

`app/jobs.py::_run_job` selects HyperFrames first by default. Preparation is in
`engine/remotion_renderer.py`; the maintained HyperFrames page is
`engine/hyperframes/product_reel.py`. A HyperFrames failure may render a Remotion
candidate, but the renderer failure is recorded and publication is held.
`REEL_ENGINE` can explicitly select Remotion. Its entry is `remotion/render.mjs`:
version 2 selects `DirectedReel`, otherwise `ProductReel`.

`brain/tts.py` requests ElevenLabs relay timestamps for Content Creator narration.
The gateway audio-only route and older files use the existing Scribe path in
`brain/transcribe_elevenlabs.py`. `engine/narration_alignment.py` caches ASR
words by SHA-256 of the audio and maps them to the script. The script owns
display spelling. Missing words, changed numbers, ambiguous word boundaries,
invalid timestamps and provider failures must not become claimed alignment.
`caption_timing.json` records per-scene evidence. Preparation runs once in the
job, so switching engines does not repeat a paid alignment attempt.

HyperFrames caption pages and active colour use measured starts and ends.
The cinematic `remotion/src/DirectedVideo.jsx` does too, including its wipe lead.
Classic DirectedReel and `remotion/src/video.jsx` animate overlay titles; they
do not show narration word captions. `word_times` is an explicit estimate only.
Any estimated scene makes the job's `caption_timing` estimated and holds the
candidate for review, even if visual QC passes.

## talking_2

The worker uses `engine/hyperframes/builder.py::build_visual_beats` and
`build_project`, `schema.py`, `renderer.py` and `engine/talking_styles/talking_2.py`.
Beats are template data. Continuous split beats group source sentences and map
their source ranges through kept shots; the legacy short-beat path also exists.
Use the current schema/catalog, not the three-type restriction from local
commit 260487f. The schema minimum is currently 0.65 seconds; admission paths
may require longer holds. Do not claim strict word-grounded speech evidence or
the old typography gates are implemented on this branch.

Motion stays in the upper panel, with the speaker below. The builder rejects
`full_frame` unless an engineer explicitly passes `allow_full_frame=True` after
obtaining permission. The normal worker does not pass it. The old
`speaker_visibility` / `cutaway_permission_evidence` schema is absent here; a
skill cannot implement that gate. Preserve the current explicit default denial.

## Persian and delivery

Keep RTL containers, joined letters, Persian digits and local Ray fonts. Animate
whole words or lines; never split Persian letters or add letter spacing. Retain
the `join_lam_alef` shaping fix. Preserve approved script spelling while mapping
ASR; digit normalization belongs upstream, not in guessed timing corrections.

Delivery is 1080×1920 at 30 fps. HyperFrames is pinned to 0.8.161 (see
`engine/hyperframes/cli.py`); Remotion packages are pinned together at 4.0.536.
Do not upgrade them as a side effect of a template change. Keep seekable paused
GSAP timelines and frame-driven Remotion animation.

`app/jobs.py` holds an existing candidate as `needs_review` when alignment,
technical/creative QC or fallback is unresolved; it clears the published output
and preserves the candidate. Failure without a candidate is `error`.
`app/talking_reel.py` similarly gates publication on technical and creative QC.
Do not add an export to versions/history before the gates pass.

## Verification

Use an installed Python environment with project requirements. Disable a local
database URL for offline tests so dotenv cannot connect to a developer database:

```sh
DATABASE_URL= python -m pytest -q tests/test_narration_alignment.py tests/test_product_reel.py tests/test_motion_contract_repairs.py tests/test_talking2_layout.py
DATABASE_URL= python -m pytest -q tests
(cd web && npm test && npm run build)
python scripts/product_caption_fixture.py --output /tmp/product-caption-fixture
ffprobe -v error -show_streams -show_format -of json /tmp/product-caption-fixture/product-reel.mp4
ffmpeg -v error -i /tmp/product-caption-fixture/product-reel.mp4 -f null -
```

The product fixture uses local macOS spoken-word audio and mocked ASR boundaries;
it spends no provider credits. It renders both templates, saves a frame sheet
around two word changes and measures decoded-frame highlight changes within one
frame. Inspect that sheet and Persian text at phone size. See
`docs/motion-caption-evidence.md` for results and limitations. For talking_2
template changes also run the opt-in real-render fixtures in
`tests/test_talking2_layout.py` (their environment flags are documented there),
inspect speaker visibility before/during/after beats, and run
`engine.hyperframes.quality.review_render` plus delivery QC. Mocks cannot prove
actual browser rendering, semantic grounding or human audio acceptance.

No runtime digest is installed: no model call on this branch consumes one.
`brain/motion_llm.py` exists only in local comparison commit b833c98. A future
typed planner would need to read/version the digest explicitly and test that it
enters the real prompt; adding a markdown file alone does nothing. Generic
upstream skill trees from 2258584 are not imported: their free-authoring routes,
auto-upgrades and newer runtime assumptions conflict with this contract.

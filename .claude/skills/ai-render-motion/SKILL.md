---
name: ai-render-motion
description: Maintain AI Render product-reel, talking_2 and talking_5 motion templates, caption alignment, export gates and their evidence. Read before changing engine/hyperframes, engine/remotion_renderer.py or remotion compositions.
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
Remotion defaults to `classic` for both config versions. `REMOTION_LOOK=cinematic`
is an explicit opt-in for the slower cinematic look; do not infer it from version 2.
`<output>.render-evidence.json` records the actual composition and look. Fixture
wipe references must come from that same React composition, with resolved props
overridden for the product-hidden reference; a HyperFrames reference is not proof
of classic Remotion product visibility.

`brain/tts.py` requests ElevenLabs relay timestamps for Content Creator narration.
Unsupported `/with-timestamps` (404/405/501 or explicit 400/422 unsupported) must
fall back once to the plain endpoint on the same relay/voice/model. Successful
audio must survive absent/invalid timing metadata; do not retry auth, credit,
rate-limit or server failures as capability rejections. The gateway audio-only
route, plain-relay fallback and older files use the cached Scribe path in
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

## talking_5 and the component registry

Keep style packs, speaker-card/matte composition, captions, hook and effects in
`engine/talking_styles/talking_5.py` and `creative/style_packs.py`. The panel
layer is `engine/hyperframes/overlay_reel.py`. It must never call an author or
execute saved `custom` HTML/CSS/JS. Legacy panels are projected to bounded typed
beat fields, rendered through the closest maintained template and recorded in
`script.json` (`component`, `template_resolution.reason`). Registry unavailable
or no equivalent: use the escaped built-in panel; keep the split shot/render.

`creative/panel_library.py` loads only its reviewed 22-component subset of
`assets/hyperframes_components/MANIFEST.json`. Models may request an allowed id
and fill bounded title/items data; never accept source, a path, arbitrary CSS,
script, or unknown variable fields. Maintained fillers and `validate_values`
restrict fields to the source's typed content schema. Escape the JSON attribute
at the mount. Verify exact source bytes, size and Apache-2.0 license before
loading; preserve vendored source/manifest/NOTICE. Job-local adapters supply
local GSAP, Ray, RTL and zero tracking, with original/adapted hashes and license
receipts. Extend the execution allowlist only after field/sink review and a real
Persian frame check; catalog membership alone does not permit execution.

`registry_pins.py` separately pins the older two talking_2 adapters. Any string
inserted in their maintained source must be JSON encoded with script-end and
attribute escaping; never concatenate model text as executable code. See
`docs/motion-template-audit.md` for the complete authored-path and sink audit.

## Persian and delivery

Keep RTL containers, joined letters and local Ray fonts. Animate whole words or
lines; never split Persian letters or add letter spacing. Retain `join_lam_alef`.
User/script/storyboard/product/beat content may contain Latin brands and models.
Apply `engine.persian_text.display_text` / `remotion/src/persian-text.mjs` only at
template display boundaries, before splitting words or caption pages. Preserve
source text, caption words and timing evidence. For each whitespace token:

- Preserve a token containing an ASCII Latin letter, including its digits (`A52`, `5G`).
- Preserve digits in the token immediately after a Latin-bearing token (`iPhone 15`).
- Otherwise convert ASCII digits to Persian digits, and a numeric token's `%`/`.`
  to `٪`/`٫`. Thus `کفش Nike Air سایز 42` renders `کفش Nike Air سایز ۴۲`.

This conservative syntactic rule does not guess model names or translate brands.
Use it on titles, item labels and caption display text in both renderers. Keep
adjacent Latin/model title tokens in one isolated animation unit (`display_units`
/ `displayUnits`) so RTL word layout does not reverse `Nike Air` or `iPhone 15`.
Keep template chrome (badges, counters, eyebrows, UI labels) Persian and mark owned
nodes `data-qc="chrome"`. Mark reviewed vendored content sinks `data-qc="content"`;
all other component text remains chrome. Only the nearest ownership marker
controls language QC. Never let model data choose ownership markers. Check chrome
even when temporarily invisible, and check visible text overflow for all content.
Mount vendored `<template>` bodies in standalone QC; inert templates prove nothing.

Later product scenes use a visible product push from 1.0 to 1.06 and headline
rise of 16px from opacity 0.6, completed within the nine-frame wipe. Keep the
photo scale cap at 1.12 and verify decoded product pixels with same-engine witnesses.
Comparison beats need two non-empty labels (or two labels split from an explicit
`یا` / `در برابر` title). Resolve underspecified comparisons to `kinetic_type`
at beat-building time and retain the reason in `why`; never pad empty boxes.

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

Keep media, frame sheets, ffprobe dumps and generated test logs outside Git.
Record hashes/measurements in `docs/motion-caption-evidence.md` and link or attach
media in the PR. Re-run product HyperFrames/Remotion and talking_2/talking_5
fixtures, verify 1080×1920/30fps/full decode, inspect frame sheets and distinguish
direct renders from a served app run.

No runtime digest is installed: no model call on this branch consumes one.
`brain/motion_llm.py` exists only in local comparison commit b833c98. A future
typed planner would need to read/version the digest explicitly and test that it
enters the real prompt; adding a markdown file alone does nothing. Generic
upstream skill trees from 2258584 are not imported: their free-authoring routes,
auto-upgrades and newer runtime assumptions conflict with this contract.

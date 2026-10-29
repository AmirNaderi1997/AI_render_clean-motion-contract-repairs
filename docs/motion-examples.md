# Five motion acceptance examples

Branch `motion-polish-v1` starts at fork `motion-captions-and-skills-v2`, `6d4071fbd4d4c85ca8983a4be5113a77667d7d9b`. Fork PRs #1 and #2 were open at branch creation. Upstream is read only. These are local, direct renders; no app UI run or live provider acceptance is claimed.

All evidence is local in `docs/motion-polish-fixture/` (ignored). Maintained fixture runner: `scripts/motion_examples_fixture.py`; adapter scan: `scripts/motion_adapter_scan.py`. HyperFrames is pinned to 0.8.161, Remotion to 4.0.536. Inputs and plans remain data; no model code is executed. No provider requests were made.

Inputs use an FFmpeg 1080×1920 / 30 fps speaker base with a synthetic face in the lower half. Local macOS Majed synthesizes individual words, concatenated with known waveform boundaries; displayed Persian digits are supplied as ASCII digits to the voice only. These timings come from construction, not ASR/provider alignment. This Arabic voice is an offline timing fixture, not Persian pronunciation acceptance. The product photos are a light-background black shoe and a dark saturated-red shoe: two footwear examples, not a single SKU photographed twice. Downloaded photos are fixture material only and are not committed.

Photo sources: [light background](https://images.unsplash.com/photo-1543508282-6319a3e2621f?w=900&q=85), [red background](https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=900&q=85).

## Inputs and beat data

1. **Kinetic speech**: `kinetic/input.json` stores transcript, word times, decisions and built beats. Spoken phrase `انتخاب بهتر در ۳ گام`; title `انتخاب بهتر`; `kinetic_type`, `assemble`, `top_panel`, full sentence window. Talking_2 uses `build_visual_beats` → `build_project` → `render_project` (real split-panel render and composition). Talking_5 uses `render_layer` with its maintained built-in kinetic panel and a real FFmpeg overlay over the same speaker base; `kinetic/talking5-input.json` records the script. This is layer/composition acceptance, not the entire talking_5 planner/face-tracking/app pipeline.
2. **Comparison**: `comparison/input.json`; spoken phrase `برای ۲ کاربرد سبک برای خانه مناسب برای سفر`; title `برای ۲ کاربرد`; items `سبک برای خانه`, `مناسب برای سفر`; `comparison`, `assemble`, `top_panel`. Uses the same real talking_2 entry points. No invented multiplier or quantity.
3. **Steps**: `steps/input.json`; spoken phrase `۳ گام برای خرید انتخاب دقیق مقایسه قیمت خرید آسان`; title `۳ گام برای خرید`; items `انتخاب دقیق`, `مقایسه قیمت`, `خرید آسان`; `steps`, `assemble`, `top_panel`. Uses the real talking_2 entry points. Badges are `۰۱`, `۰۲`, `۰۳`. Additional browser regressions cover four long Persian steps and long comparison labels at the real panel dimensions.
4. **Hero**: `product/hero-input.json`; version 2, one photo scene, title `انتخاب بهتر`, narration `انتخاب بهتر برای ۲ کاربرد`, constructed caption word times. Real `product_reel.render` and `remotion_renderer.render` with cinematic look, plus retained project reconstruction for DOM evidence.
5. **Promo**: `product/promo-input.json`; version 2, three photo scenes alternating light/red/light, titles `انتخاب بهتر`, `برای ۲ کاربرد`, `همراه هر روز`, same fixture narration on each scene. A common accent and nine-frame wipes connect the scenes. This repeated short narration tests media/timing/transition plumbing; editorial script and pronunciation still need human review. Both real product renderer entry points are used. Fallback equivalence means the same framing, visible incoming content, typography and caption placement; sparkles/easing/edge styling are not pixel-identical.

## Render evidence

Each sheet contains start + one frame, midpoint and end - one frame for every beat/scene, followed by the midpoint of each wipe where present. Every output was probed as 1080×1920, `30/1`, with an audio stream. Full probes, QC JSON, inputs and decoded wipe witnesses are alongside the sheets. Single talking beats/hero have no inter-scene transition to sample.

| Example / renderer | SHA-256 | QC | Frame sheet |
|---|---|---|---|
| kinetic | `be1a965420afe987cbdc8dc3a46dc4b23fa475313a944d8d2a51b755035dc84c` | passed | `docs/motion-polish-fixture/kinetic-sheet.jpg` |
| kinetic-talking5 | `4af55bf912e014532d704b45fc180e6aaf3f9ae95e13098bf81b5c3af31d3a0b` | passed | `docs/motion-polish-fixture/kinetic-talking5-sheet.jpg` |
| comparison | `b7e2a99a59452ad4d93078877f6385444b8aa347c1503bc30be72e7e85ba30cc` | passed | `docs/motion-polish-fixture/comparison-sheet.jpg` |
| steps | `d733efc9684d44f68774315ab8beb547ffb121c0f9cf71c708078e8f4a297ee8` | passed | `docs/motion-polish-fixture/steps-sheet.jpg` |
| hero | `1ac3449e6ee48c3ba8817d113fe5ab754d396d8d6f43fc7262c733794d85ae4f` | passed | `docs/motion-polish-fixture/hero-sheet.jpg` |
| hero-remotion | `857634f8dfbad5c51e986d9053e2720554e5af6bc7fa858a1b050679894b0b65` | passed | `docs/motion-polish-fixture/hero-remotion-sheet.jpg` |
| promo | `e561b031481e2088f058d335b80302fa0b813b12b93055859ca5d014da865980` | passed | `docs/motion-polish-fixture/promo-sheet.jpg` |
| promo-remotion | `dc61e3bc65fcbe914d8035adbb5fe1384baaae9dce0686884e8eea3bbe171ebb` | passed | `docs/motion-polish-fixture/promo-remotion-sheet.jpg` |

QC checks the maintained generated DOM for Latin letters/digits (including temporarily invisible copy), and uses browser text ranges and clipped scroll boxes to find panel overflow. Missing browser evidence fails closed. Wipe QC creates normal/product-hidden browser references and requires product-specific pixel differences in the actual encoded video frame. It is sampled evidence, not all-frame semantic vision/OCR. Raster photo branding is outside the DOM language check. Talking_2 invokes DOM QC through `review_render`; product render invokes it before cleanup and holds a candidate on failure. An app regression ensures a QC hold does not trigger a fallback render.

The 22 enabled adapters were scanned at four times each, at their actual zoom-adjusted panel dimensions: zero language/layout/runtime findings (`adapter-scan/results.json`). `beat-timeline` and `pan-stations` were already excluded on this base and remain excluded. Vendored bytes and hashes were not changed. Scan exercises representative supplied content, not every possible input. The talking_5 acceptance uses its maintained built-in panel.

Decoded mid-wipe product pixel counts:

- promo: 692410, 595856.
- promo-remotion: 690299, 594967.

Face-region check: mean RGB pixel differences from the base in `(300,1050)–(780,1750)` at each midpoint: {"kinetic": 0.1175, "kinetic-talking5": 0.2234, "comparison": 0.1198, "steps": 0.1199}. Minor differences are encoder noise; the graphic stays above the face. See `face-region-difference.json`.

## Verification and remaining review

- `DATABASE_URL='' REDIS_URL='' /tmp/pr4-review-venv/bin/python -m pytest -q tests`: **740 passed, 10 skipped**. The empty URLs select isolated local test storage; an initial run against the developer environment's absent PostgreSQL failed. `jsonschema` was added to production requirements and the Docker lock, with its dependency pins. Browser layout tests require the npm/browser installation.
- Frontend `npm test`: **92 passed**; `npm run build`: passed, with the existing large-chunk advisory.
- Rendered sheets inspected for joined Persian text, supplied comparison labels, Persian badges, unobstructed face, preserved photo boundaries and incoming product/title presence. QC also ran deliberate failure regressions for English/digits, overflowing text and a missing product in a wipe.
- These are direct renderer fixtures, plus mocked app worker/publication regressions. No full app UI run, fresh paid TTS/STT, native Persian listening approval, real speaker face tracking, or deployment was performed. Human review still needs full-speed motion, natural Persian audio, phone readability, caption sync perception and final art direction. Product short-world warnings (`fewer than four visual worlds`) are expected for these one/three-scene fixtures and are not failures.

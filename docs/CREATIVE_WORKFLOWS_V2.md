# Creative workflows v2 — repository audit and implementation contract

Audit date: 2026-10-21. Baseline: `90724d0`, plus pre-existing uncommitted browser-render work (not part of this change).

## Observed execution, not the product vision

| Boundary | Actual authority | Gap |
|---|---|---|
| Chat, auth, ownership, history, SSE | `app/routers/studio.py`, `studio_store.py`, existing DB models | Preserve contracts and persisted events; no new agent service/database. |
| Intent and execution | `app/studio_orchestrator.py`, typed `studio_tools.py` | Six intents select real engines, not a general tool loop. Motion revision currently creates a new job and repeats planning. Localize revision currently ignores the requested edit and changes voice provider. |
| Ideation | `creative/director.py`, `schemas.py`, `prompts.py` | Real brief / concepts / critique / expansion already exist. Most direction reaches execution as prose. Images are classified by request word count. Missing asset evidence at direction time. |
| Talking | `app/talking_reel.py`, `brain/talking_reel*.py`, four native styles | Real transcript and renderer. Split-style planner can synthesize generic filler B-roll. HyperFrames QC can fail twice and still reach `done`. |
| Motion / text / images | `brain/content_creator.py`, `storyboard.py` | Actual generation checkpoints, source photo inspection, narration, native/Remotion assembly. A second storyboard model can discard the selected concept. `_motion_prompt` always requests an advertisement. Missing creative endpoint-to-export contract. |
| Reuse | `generation_checkpoint.json`, `authored_scenes.json` | Whole storyboard hash invalidates all media; authored scene cache uses start time alone, so changed text can reuse stale artwork. |
| Localize | `app/localize.py`, `brain/localize.py`, `engine/localize.py` | Real OCR tracks, translation, narration and covers. Not general graphic recreation/inpainting; cannot promise it. No output-level creative review. |
| Quality | `technical_qc.py`, `hyperframes/quality.py`, `brain/qc_pipeline.py` | Technical checks exist; deterministic visual variety is not creative judgement. Existing vision review loses provider failures as an empty issue list. Need evidence-bound review with explicit unavailable state, no automatic paid regeneration. |
| Providers | `brain/lm_gateway.py`, `lm_tasks.py`, media/TTS adapters | Reuse operator routes and capability checks; do not hardcode suggested model names or add another SDK. |

## Flow contracts

A: transcript → evidenced brief/concepts → anchored creative beats → existing style decisions → native cut + selected graphics → output review.

B: URL/user facts + visually reviewed assets → sales concept → typed executable storyboard → approval → existing asset/narration/render path → output review.

C: idea → genre-specific concept → executable storyboard (not forcibly an ad) → approval → asset/narration/render path → output review.

D: images → actual image evidence → image-led concept and shot progression → executable storyboard → approval → same path.

E: existing OCR/translation/cover/dub pipeline → output review. Unimplemented graphic reconstruction stays explicitly unsupported, not a new marketing claim.

F: existing project → validated, bounded patch → immutable storyboard snapshot → component fingerprints → approval → reuse unchanged assets/voices → new output version.

## Implementation order and constraints

1. Preserve rich creative state and bind scene instructions to verified assets and sentence IDs. Prefer a single validated plan over a second unrelated planning pass.
2. Fix dependency-aware reuse and in-place conversational storyboard revision. Preserve all older output versions and require confirmation for generation.
3. Add actual-output creative review through the existing `visual_qc` gateway route. Evidence is sampled frames + plan, not imagined footage; do not claim audio listening from pictures. Provider failure is `unavailable`, never a clean pass.
4. Gate new v2 creative outputs on review, preserve old jobs. No automatic paid media retries; improvement proposals require user approval.
5. Test pure contracts separately from actual FFmpeg/media tests and real-provider tests. Passing mocked provider tests does not establish professional quality.

## External projects

The five user-linked repositories were reopened during this audit. Existing `docs/OPEN_SOURCE_REVIEW.md` records provenance/licensing analysis; Tscaps MIT engine and templates are already integrated (`tools/tscaps`, `engine/tscaps_overlay.py`). AIEV/AutoBroll are references, not installed EditorGPT engines. Remotion is installed and called by `engine/remotion_renderer.py`; the third-party agent-skills repository is not an installed execution engine. HyperFrames is pinned and has actual native/sparse rendering adapters. Do not copy unlicensed code, stock assets, or the AGPL studio into this application.

## Acceptance status

This document is an audit/implementation specification, not evidence that six professional creative workflows have passed acceptance. Record test commands, fresh output evidence, provider tests and remaining gaps below when implemented. Human comparison of representative final videos remains necessary; a model score alone is not acceptance.

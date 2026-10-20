# Creative Engine audit — what the code and the real jobs show

Date: 2026-10-20. Repository state: `main` @ `a7d6ded` (the backend running on `:8000` is the same commit).
Evidence sources: source code, the live job store (`jobs/local_dev/data`), the gateway call log
(`ai_gateway/state.json`), and the Studio store (`studio/studio.json`). Nothing below was inferred from
the vision document alone.

## 1. How a request flows today

```
chat message ──► _resolved_intent()  (LLM classifier, 6 labels; regex fallback)
                   │
   ┌───────────────┼──────────────────────────────┬───────────────────────────┐
   ▼               ▼                              ▼                           ▼
 localize      talking                         motion                      modify
 (engine/      (app/talking_reel.py:           (_create_motion:            (_modify: keyword
 localize.py)   _analyze → talking_1..4)        one storyboard prompt →     regex on the text)
                                                 Arvan image per scene →
                                                 local Ken-Burns/HTML render)
```

The "agent" is a 6-way classifier plus fixed pipelines. Each pipeline makes **one** LLM call to decide
everything (`brain/talking_reel.py:decide`, `brain/storyboard.py:generate_storyboard`).

## 2. Findings per problem in the product brief

| # | Problem (brief) | What the code actually does | Evidence |
|---|---|---|---|
| 1 | No real intelligence | Fixed routes. Style is asked from the user although the engine can choose: `app/talking_reel.py:_analyze` already calls `recommend_style()` when `style` is empty, but the Studio orchestrator always asks (`question.required … kind=talking_style`). "Modify" is keyword matching: `"زرد"`, `"zoom N"`, `"لوگو"` (`_modify`). Anything else raises *"this change is not mapped yet"*. | `app/studio_orchestrator.py` `_modify`, `_style` |
| 2 | Fixed / mock flows | Four hard-coded Talking styles (`engine/talking_styles/talking_1..4`) and one storyboard prompt. A revision of a motion project re-creates the whole storyboard (`_create_motion(... "Requested revision")`). | `_modify`, `engine/talking_styles/` |
| 3 | Primitive motion | `engine/motion_recipes.py` = 20 recipes mapped to 11 HTML "families" (`engine/hyperframes/builder.py:_beat_markup`). Recipes are chosen by a deterministic scorer, not designed per scene. The Remotion path is one 79-line composition with `index % 3` layout switching (`remotion/src/video.jsx`). | `motion_recipes.py`, `video.jsx` |
| 4 | Talking edits not engaging | Talking_1 = captions + zoom + hook + 1–3 B&W moments + ≤2 notes. Only Talking_2 adds picture "beats". No concept stage; the model edits text and picks indices. | `brain/talking_reel.py` |
| 5 | Weak B-roll | Beat images are generated from a generic style prompt ("Swiss editorial vector illustration…", `brain/talking_reel_2.py`); no semantic matching to speech timing beyond the sentence index; no stock/screenshot/chart sourcing; `grep stock` finds only prompt text. | `talking_reel_2.py`, `app/talking_reel.py:597` |
| 6 | Imprecise localization | OCR exists (`engine/localize.py`: tesseract sampling at 4 fps, caption-region detection) but only for *burned-in captions*; text inside graphics is covered with a box, not removed/redesigned. | `engine/localize.py` |
| 7 | No creative storyboard | One prompt asks a single call to be "creative director". No audience/pain/USP analysis step, no alternative concepts, no critique. Product facts are extracted well (`_page_brief`) but then flattened into prose. | `brain/storyboard.py`, `_motion_prompt` |
| 8 | No creative QA | A vision QC exists (`visual_qc`, `brain/qc_review.py`) but only the HyperFrames talking path calls it at 99 %; motion (Content Creator) and Localize outputs are never reviewed. | `app/talking_reel.py:756` |

## 3. The creative model-routing bug (largest quality lever)

`brain/lm_tasks.py` defines a thoughtful task policy: `edit_planning`/`hyperframes_design` → Opus-class,
`storyboard_generation`/`script_generation` → Sonnet-class. **No code path calls those task routes.**
The creative calls go to the parent routes:

| Call site | Route used | What it resolves to (live config) |
|---|---|---|
| `brain/talking_reel.py:_chat` | `editing_agent` | was `auto` (hung 90 s); now Gemini-3.5-Flash/DeepSeek-Flash (light models) |
| `brain/ai_provider.py:359` (storyboard) | `script` | `auto` → on the logged call **`mistral-small-3.1-24b`**, 29.9 s |
| `app/studio_orchestrator._page_brief` | `editing_agent` | light model |

So the 30-second Persian ad script was written by a small model chosen by an unpinned `auto` router, while
the Opus/Sonnet routes sit unused (and are `['auto']`, 90 s, 0 retries in the live config).

## 4. Where builds actually get stuck (real jobs and logs)

Studio has 5 projects; the generic job store has 12 jobs. Terminal states:

| When | Engine | Outcome | Root cause |
|---|---|---|---|
| 10-20 01:04 | talking_1 | **error @30 %** `LM API ReadTimeout` | `editing_agent` on `auto`, 90 s, `max_retries=0`, no fallback. Transcription took ~12 s; the single LLM call is the bottleneck and a single point of failure. (Since changed by the operator to Gemini + 180 s.) |
| 10-20 01:53 | motion | **failed, 0/7 scenes** `Arvan returned no inline image` | Image route `Gemini-3.1-Flash-Image-Preview` returned no image on scene 0 (13 s); one provider, no retry, no alternate model, job dead. Scene prompt was also generic ("a sleek modern product against a white background") — the storyboard had no product evidence. |
| 10-18 19:57 | talking_2 | **error @98 %** `HyperFrames render failed … sub_timeline_script_failure` | The composition loads GSAP from `https://cdn.jsdelivr.net/...` at render time (`engine/hyperframes/builder.py:321`). The script failed to load **after 1347/1347 frames were encoded (126 s)**; the pre-render `check` had passed. A network dependency destroyed two minutes of work. The surfaced message is the last 500 chars, which hid the cause. |
| 10-18 19:02 | talking_2 | **error @47 %** `Interrupted by a server restart` | Renders run in daemon threads in the API process; a restart kills them and there is no resume. |
| 10-15 01:52 | talking_1 | error @5 % ElevenLabs key/VPN | Transcription depends on a provider that is unreachable without VPN; preflight did not catch it before upload. |
| — | talking_1 / motion | done (3 + 2) | The fixed pipelines work when providers answer. |

Gateway log (all recorded calls): `editing_agent` 1/1 failed (90 s), `general_chat` 3/20 failed (429, 503, 503 in
a 45-second burst on the Sonnet route), `image` 1/1 failed, `script` 30 s. There is a retry budget of 0 on every
route.

Pattern: **one provider call per decision, no retries, no alternates, no checkpoints after the cheap part, and
late-binding external dependencies.** These cost more user time than any quality issue.

## 5. Status of the named open-source projects

Searched code, docs and JSON for `AIEV`, `autobroll`, `tscaps`, `remotion-agent-skills`: **no hits**.

| Project | State in the repo |
|---|---|
| HyperFrames (official) | *Partially present.* CLI pinned (`0.8.161`), full catalog **metadata** snapshot (`catalog_index.json`), and a local renderer that executes only 11 audited HTML adapters. The catalog is a "design vocabulary", not executable. |
| Remotion | *Minimal.* `remotion/` has one composition used by the Content Creator render. |
| AIEV, AutoBroll, Tscaps, Remotion Agent Skills | *Not integrated.* Each needs a licence/API review and an integration spike before it is called supported. |

## 6. What is good and should be kept

Typed tool registry with `extra="forbid"`, SSRF-safe URL inspection, persisted events with resume, ownership
checks, deterministic renderers with real QC hooks, word-level transcripts, `segment_analysis`, the OCR
region detection, the gateway's audit log. The right move is to add a creative layer above these and fix the
reliability seams, not to replace them.

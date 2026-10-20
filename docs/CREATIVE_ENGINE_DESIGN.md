# Creative Engine — design, status, and next steps

Companion to [`CREATIVE_ENGINE_AUDIT.md`](CREATIVE_ENGINE_AUDIT.md). Facts there; decisions here.

## 1. Principle

Three layers, one rule: **the creative layer may improve a result but may never be the reason a job fails.**

```
chat ─► AI Video Agent (app/studio_orchestrator.py)     decides WHAT to run, owns conversation & jobs
              │
              ▼
        Creative Engine (creative/)                       decides HOW the video should be made
          understand → ideate (3 concepts) → critique → expand → CreativePlan
              │  director_notes + style + beats
              ▼
        Render engines (Talking, HyperFrames, Content Creator, Localize)   execute
              │
        AI Gateway (brain/lm_gateway.py)                  models, routing, retries, audit
```

Every creative call goes through the existing gateway on its own routes (`creative_director`,
`creative_critic`, `creative_revision`, registered in `brain/lm_tasks.py`). If a call fails the caller
receives `CreativeUnavailable` and continues with the standard pipeline, saying so in the conversation.

## 2. What is implemented (this branch)

| Piece | Where | Status |
|---|---|---|
| Brief understanding, 3 compact concepts, harsh critic, expansion of the winner | `creative/director.py`, `prompts.py`, `schemas.py` | **Done, run against the real gateway** |
| Truncation/rate-limit/timeout resilience for creative calls | `creative/llm.py` | Done (retries with a bigger budget; waits out ≤60 s cooldowns) |
| **Flow A** talking video: director picks style + guidance; engines receive `guidance` | `app/talking_reel.py:_analyze`, `brain/talking_reel*.py` | **Done**, end-to-end render verified (see §4) |
| Style no longer asked from the user | `app/studio_orchestrator.py` | Done (explicit style in the message still wins) |
| **Flows B/C/D** product / text idea / images → storyboard driven by the chosen concept | `_creative_direction`, `_motion_prompt` | Done in code and unit-tested; not yet rendered end-to-end (see §5) |
| **Flow F** conversational revision → typed ops → only affected state changes | `creative/revise.py`, `_revise_talking` | Done for Talking projects; interpreter run on the real gateway |
| Decision-call resilience (retry on 429/5xx/timeouts, cooldown-aware) | `brain/llm.py:gateway_json_resilient` | Done |
| Image generation: bounded retry and the model's own reply surfaced | `brain/media_provider.py` | Done |
| HyperFrames: GSAP no longer loaded from a CDN at render time; integrity-checked cache; failure cause shown first | `engine/hyperframes/{assets,builder,renderer}.py` | Done |
| Direct provider fallbacks (Sarovi, Jarvis, Arvan, OpenAI, Gemini via Vercel proxy) when LM API fails; admin tab with write-only keys, order, per-provider and master switch, test button | `brain/lm_direct.py`, `app/routers/lm_admin.py`, `web/src/AIDirectFallbacks.tsx` | Done; tested incl. the real Jarvis endpoint reached with a fake key |
| Evaluation harness | `scripts/creative_eval.py` | Done |

Switch off with `CREATIVE_ENGINE=0`.

## 2b. Honest verdict on visual quality (from real renders)

Contact sheets of the two real renders show the limit clearly: the director's *thinking* improved (specific hook,
faithful beats, differentiated concepts), but the *pictures* did not, because every renderer draws from a fixed set of
templates. Talking_1 is one look (zoom, pinned hook, B&W takeaway). Talking_2's cards are full-screen text/diagram
inserts; its "media collage" card renders as empty beige rectangles. A director that can only choose among these will
always produce "the same video". Fixing this needs a generative motion layer (§6, item 1), not better prompts.

## 3. What is **not** implemented (said plainly)

* **Flow E, intelligent localization.** The OCR in `engine/localize.py` finds burned-in captions; text inside
  graphics is covered, not translated and redesigned. Needs: full-frame text detection with a vision model,
  per-region translation, inpainting/cover plates, retyped Persian typography with the same box and timing, and a
  verification pass. This is a multi-week engine task; no code here.
* **Creative review after render** (problem 8). `visual_qc` exists for the HyperFrames talking path only. The
  plan is a `creative/review.py` that samples frames (`engine/qc_sampler.py`), scores them with a vision route
  against the chosen concept and brief, and triggers one targeted fix. Not built.
* **New visual vocabulary** (problems 3–5). The director now plans with the 20 existing recipes and 4 existing
  styles; it cannot create motion those renderers do not have. Better motion needs new renderers (§6).
* **Partial re-render.** Revision applies only the changed fields, but the Talking engine still re-renders the
  whole video; storyboard-scene-level re-render for Content Creator is not built.
* **Open-source projects** (§6): none of AIEV, AutoBroll, Tscaps, Remotion Agent Skills is integrated.
* **Studio UI** for concept alternatives and the new stages is not part of this branch.

## 4. Evidence

All numbers from runs on this machine against the real gateway (Persian talk, 47 s, 6 sentences):

| Run | Result |
|---|---|
| Director on DeepSeek-V4-Flash (Gemini 429, Sonnet 503) | 104 s; 3 genuinely different concepts; critic chose the most buildable and faithful; honoured `must_not` |
| Director on Opus 5.5 (Jarvis, after probe) | 127 s; sharper critique (noticed an unprovided-logo risk, a repeated recipe, a cold-open the style lacks) |
| Full Flow A on the job that previously died at 30 % (`LM API ReadTimeout`) | analysis 135 s + render 88 s = **223 s, done**; 1080×1920 H.264/AAC, 47.3 s; hook, highlights, B&W takeaway tied to the chosen concept |
| Revision interpreter, compound request (hook + cinematic grade + less zoom) | 3 correct typed ops, hook grounded in the video's real content |
| Revision interpreter, unsupported request (sad music, child voice) | no ops, honest explanation |
| Backend tests | 47 → 68, all passing |

Observed provider behaviour that shapes the design: the gateway returned Sonnet 503/429, Gemini 429 and DeepSeek
502/503 in bursts; reasoning models spent the entire output budget (7000 and 10000 tokens) on a single large
JSON, truncating it. Hence compact proposals + expansion of only the winner, retries that raise the budget, and
cooldown-aware waits.

## 5. Flows A–F

| Flow | Input | Director output | Executor | State |
|---|---|---|---|---|
| A Talking | video | brief, concept, style, per-beat visual ideas anchored to sentence indices | Talking styles 1–4 (+HyperFrames beats for 2) | working |
| B Product/service | URL / text / images | sales-logic concept: problem → proof → CTA, only verified facts | Content Creator storyboard → render | code + tests; needs a real render pass |
| C Idea | text | genre-appropriate arc | same | code + tests |
| D Images | images | order, crops, motion progression | same | code + tests |
| E Localization | foreign video | — | Localize | **not started** |
| F Revision | chat message + project | typed ops (`creative/revise.py`) | `talking_reel.update/start` | Talking done; motion/localize fall back to the old path |

## 6. Roadmap, in order of expected quality gain per effort

1. **Pin strong models** (operator, no code): in *AI Models → Routing* set `creative_director`/`creative_critic`
   to Opus-class, `creative_revision` and `storyboard_generation` to Sonnet-class, add a second provider as
   fallback, `max_retries` 1, timeout 150–180 s. Probe each model once (the gateway requires it). The storyboard
   was being written by `mistral-small` through an unpinned `auto` route.
2. **Creative review loop** (`creative/review.py`) for Talking and Content Creator outputs.
3. **New talking style modules** (`talking_5…`), because saved styles are frozen by policy. The director's beats
   map to them: each new style adds renderable vocabulary (kinetic hooks, concept diagrams, data cards, B-roll
   with real motion) instead of tuning prompts.
4. **B-roll director**: per-beat choice between generated still, screenshot/product image, chart, or motion
   scene; AutoBroll is the candidate for semantic matching and timing. Needs a licence + API spike first.
5. **Animated captions**: Tscaps spike against the current ASS pipeline.
6. **AIEV / Remotion Agent Skills**: read for direction ideas; integrate only what has a deterministic renderer
   and an API we can run headless.
7. **Flow E**: described in §3.
8. **Resume after restart**: renders run in daemon threads; persist stage checkpoints and resume on boot.

## 7. Evaluation (how quality will be judged)

`scripts/creative_eval.py <transcript.json>` prints brief, concepts, scores, verdict and the notes the engines
receive. The acceptance test is a human one: render the same inputs with `CREATIVE_ENGINE=0` and `=1` and
compare the two videos side by side. Automatic scores are for regressions only.

## 8. Operational notes

* GSAP is downloaded once from the npm registry, verified against the registry's sha512, cached under
  `JOBS_DIR/.cache/hyperframes/` and copied into each project. It is not committed (the repository is public;
  GreenSock's licence).
* New routes are created automatically on first use and inherit the parent route's models; they appear in
  *AI Models & Logs*.
* Failure messages from HyperFrames now lead with the cause instead of the last 500 bytes of CLI JSON.

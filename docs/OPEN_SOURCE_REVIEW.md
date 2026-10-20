# Open-source review — what we took, what we left, and why

Reviewed on 2026-10-20 from the repositories themselves (code, licences, assets), not from their READMEs alone.
"Licence" is what the file in the repo says; this is engineering triage, not legal advice.

| Project | Licence (verified) | Verdict | Used now |
|---|---|---|---|
| [AIEV](https://github.com/notivn/AIEV) | MIT; **its sound-effects library has no provenance** | Adopt ideas and structure; do **not** copy its audio | Sound design (synthesised), sparse-cue policy, resume/queue ideas on the roadmap |
| [AutoBroll](https://github.com/andriidrok1/autobroll) | MIT | Adopt the B-roll policy and the fullscreen/inset/top modes; build our own planner | Policy captured below; planner is next |
| [Tscaps](https://github.com/francozanardi/tscaps) | **Mixed:** `packages/engine`, `templates/`, `skills/` are MIT; `apps/studio` and the repo root are AGPL-3.0 | The engine and the 38+ caption templates **can** be embedded; the studio app cannot | Not yet; integration plan below |
| [Remotion Agent Skills](https://github.com/phamthanhnghia/remotion-agent-skills) | No licence file | Do not copy; read-only inspiration | Nothing |
| [Remotion](https://github.com/remotion-dev/remotion) | Source-available; companies above 3 people need a paid licence | Keep out of the critical path; HyperFrames (Apache-2.0) is the renderer | Nothing new |
| [open-design](https://github.com/nexu-io/open-design) | Apache-2.0 | Adopt the craft rules for authored design | Already in the Motion Designer prompt (typography scale, one accent, no gratuitous gradients, spacing rhythm) |

## What this branch now does with them

**Sound design (from AIEV's idea, not its files).** AIEV mixes whooshes and hits on scene beats, and it is a big part
of why its edits feel produced. Its sound library, though, says plainly that the files were "collected over years from
assorted sources with no licensing records", so we did not import it. `engine/sfx.py` synthesises a whoosh, hit, pop,
tick and riser with ffmpeg (noise and sine envelopes). They are placed as `<audio>` clips in the HyperFrames project:
a whoosh as an authored scene arrives, a soft hit as its main word lands, a whoosh as the speaker returns. Quiet by
design; templates-only renders get no effects.

**Full-frame backdrop.** The renders showed black bars around the shrunken speaker (picture-in-picture). Every
authored scene now carries a backdrop in the design system's background colour, so the whole frame is designed.

**Scene cache.** Authored scenes are stored next to the job (`talking_reel_work/authored_scenes.json`, keyed by beat id
and start time). A re-render, a retry or a render-only rerun never pays for authoring again.

## Tscaps — the one with the most to give

The README's AGPL badge hides the useful part: the **engine** (`@tscaps/engine`) and the **template gallery** carry
their own MIT licences. That changes the verdict from "ideas only" to "can be integrated".

What it would give us, in order of value for talking videos:

1. **Hook and caption typography.** 38+ looks (modern, key moments, viral, classic) with per-word emphasis, entity
   tagging, quote colouring and word-level timing. Our captions are one ASS style.
2. **Persian/RTL.** The engine resolves mixed-direction text through the Unicode bidi algorithm, which is exactly where
   ASS captions break.
3. **Text behind the speaker** (on-device person segmentation) — the effect that makes talking videos look expensive.

Why it is not wired in yet: the engine renders in a browser (DOM → bitmap per frame → WebCodecs), not in our Python
pipeline. Two honest routes:

* **Browser-driven overlay render**: run the engine in the headless Chromium we already use for HyperFrames, export a
  transparent caption layer, and composite it in the HyperFrames project. Needs a spike (frame accuracy, alpha,
  Persian fonts) before it is promised.
* **Port the template vocabulary** into the Motion Designer's caption archetypes (CSS/GSAP). Cheaper, loses the engine's
  word timing, keeps one renderer.

Recommended next step: a one-day spike of route 1 on the Persian sample; keep route 2 as the fallback.
Each template folder has its own `template.json` + `style.scss`; third-party fonts must be checked individually.

## AutoBroll — policy to adopt

Its B-roll prompt is short and right: **one visual per 8–12 s of speech**, only for concrete, visualisable nouns,
prefer the creator's own footage, otherwise a 2–4 word stock query; three placements — *fullscreen* (cutaway, ~2 s),
*inset* (small corner, face stays visible), *top* (upper half). It sources stock from Pexels (smallest mp4 at least
as tall as the output).

Our gap is real: B-roll today is a generated still with a generic style prompt. Plan (`creative/broll.py`, not built):
planner call using the policy above; sources in order — user uploads, Pexels (needs `PEXELS_API_KEY`, none configured),
generated stills; placement via the existing authored-scene `speaker` modes (`pip` ≈ inset, `hidden` ≈ cutaway).
AutoBroll's editor UI (timeline, inspector, draggable captions) is a React/Remotion app; our Studio already owns the
conversation, so we take its interaction ideas, not its code.

## AIEV — other ideas worth taking

* A render queue with persisted progress and **resume after interruption** (our renders die with the server; roadmap).
* Style/brand kits applied to every output (our design systems are per-job; making them reusable is small).
* Colour-grading presets with per-frame preview, and key-word layout in an upper band (ideas for later scenes).
* Skills as markdown managed in the UI — we keep ours in code for now.

## Remotion and Remotion Agent Skills

Remotion's licence makes it a business decision; HyperFrames already renders our scenes under Apache-2.0, and the
Motion Designer authors HTML/GSAP which HyperFrames validates and renders. The agent-skills repo has no licence, so
nothing was copied. If the team later buys a Remotion licence, AutoBroll/AIEV compositions become portable.

## open-design

Apache-2.0. Its value is craft rules, not code: constrain typography to a scale, one accent colour, consistent
spacing, avoid default AI gradients. They are in the Motion Designer's prompt and its static validator (for example,
no negative `letter-spacing` on Persian text). Attribution belongs in the README if more is copied.

## Tscaps spike result (2026-10-20)

Question: can the MIT engine render Persian captions headlessly in our environment? **Yes.**

* `@tscaps/engine@0.7.0` from npm + Vite + Playwright driving the installed Chrome, our own word timestamps fed through
  `PassthroughTranscriber` (no Whisper download).
* 12 s of the Persian sample, 1080×1920, five templates (hugo, milo, cleo, noor, enzo): **2–17 s each** (360 frames),
  H.264 + AAC out.
* Persian is correct: joined letters, right-to-left word order, per-word timing. Our Ray and Vazirmatn fonts apply
  through a CSS override.
* Templates are authored as SCSS with a build step whose helper functions live in the AGPL `apps/studio`. For the spike
  we ran that build in a scratch checkout; **we did not copy it into this repository.** Productising means either
  vendoring the already-built `style.build.css` files (MIT, derived from MIT sources) or writing our own SCSS helpers.
* Not yet tested: text behind the speaker, emoji, per-word emphasis tags, burning onto the full HyperFrames output.

## Tscaps integration (shipped on `creative-engine`)

**How it works.** `tools/tscaps` runs the MIT `@tscaps/engine` in headless Chrome (Playwright) and writes a
*transparent* VP9 WebM that contains only text. The engine paints captions onto a blank video, and a thin wrapper makes
it use its own "transparent background" mode, which the public builder does not expose. `engine/tscaps_overlay.py`
plans the cues and calls it; the talking renderers composite the layer with one extra `overlay` in their ffmpeg graph,
so the video is still encoded once.

| Style | Drawn by Tscaps | Stays built-in |
|---|---|---|
| talking_1 | key moments (emphasis phrases) | the old caption system, the pinned hook box, name/title, B&W treatment |
| talking_2 (and its HyperFrames rough cut) | the opening hook | captions, chips, picture cards |
| talking_3 | the hook and the chapter-title key moments | captions, chips |
| talking_4 | **captions, hook and key moments** | nothing (it replaces the plain subtitles) |

Looks (Persian-safe: our Ray/Vazirmatn fonts, zero letter-spacing, right-to-left): captions `loki` (calm white, the spoken
word lights up), hook `noor` (gold glow), key moment `elio` (large white). More are one CSS file away
(`tools/tscaps/templates/`, see `NOTICE.md`; 41 were tried on the Persian sample).

**Safety.** A reel never depends on it: no Node, no Chrome, a failed engine run or a failed composite all fall back to
the style's own ASS text (tested). `TSCAPS_OVERLAY=0` switches it off; `TSCAPS_CHROME` points at a browser; the
Dockerfile installs the tool and sets `TSCAPS_CHROME=/usr/bin/chromium`.

**Not verified:** Debian's Chromium in the container (alpha VP9 encoding through WebCodecs). If it cannot encode, the
fall-back applies and nothing breaks, but captions would look as before.

**Not done:** non-talking videos (the Remotion product reel). Its scene titles are designed light cards; a white-text
overlay does not belong on them, and recolouring them is a design pass of its own. Text behind the speaker is also not
used yet.

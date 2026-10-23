# Creative script engine — root causes and the new pipeline

Scope: videos with no speech of their own (idea, product/URL, images). Talking-head projects keep the speaker's words.

## What went wrong before (evidence from the failing project)

Project `70c41b10…` (a 60-second documentary from a Wikipedia article), job `1f225664b34b` on the server:

| Symptom | Root cause | Where |
|---|---|---|
| The script was commentary about the article's *reliability* ("full text and sources are not available here") instead of the war analysis | The page extractor returns every text node in order; the article body started at node ~89 and the storyboard prompt used `page["content"][:80]`, so the writer received the site menu and none of the article. The facts step used `[:120]`, a sliver of it. | `app/studio_orchestrator.py` (`_motion_prompt`, `_page_brief`) |
| Short, vague, "filler" lines | Narration was one field (`narration`) of a single `EXPAND` call that also had to plan visuals, motion and titles. Nothing wrote the script as a script. | `creative/director.py::_expand`, `creative/prompts.py::EXPAND` |
| Every concept critique looked fine, the script still weak | The critic scored three one-line *concept sketches*; the written script was never criticised. | `creative/prompts.py::CRITIQUE` |
| Scripts overran or were cut to fragments | Length was checked with a word count (`len(narration.split()) > int(seconds*2)`); Persian speech time is not a function of word count (4 words = 1.4 s or 2.8 s). Real TTS audio was never compared with the plan. | `creative/production.py` (old rule), `brain/content_creator.py` |
| Reference ignored, then half-claimed | Social links were stripped from the request and a note told the model "do not claim anything"; no video was ever downloaded or analysed, and the user was not told to upload a file. Attached videos were ignored in this flow. | `app/studio_orchestrator.py::_create_motion` |
| Repeated, mechanical chat narration | Every model call announced itself in chat at start and again every 30 s. | `app/studio_activity.py` (fixed earlier) |
| Failures were swallowed | `RemoteProtocolError` (dropped connection) was fatal for a creative call; the director then silently fell back to outline-only beats. | `creative/llm.py` |

## The pipeline now

`creative/director.py::_direct` → for non-talk kinds:

1. **Brief** (`ContentBrief`, now with `must_name`: the 2–4 terms a viewer must *hear*).
2. **Angles** (`PROPOSE`): three concepts that differ in hook, message and ending, each with a named structure from `STRUCTURES`, a payoff and a target feeling.
3. **Concept critique** picks one (unchanged).
4. **Script** (`creative/script.py::run`) replaces the single expansion call:
   - *write*: Persian spoken script + under every line what is **heard / seen / why / focus / link to the previous scene** (visual-first);
   - *measure* (no model): Persian speech seconds (`creative/speech.py`, fitted on 18 real ElevenLabs clips, MAE 0.36 s), scene count, clichés, lines without a concrete picture, the topic being spoken (`must_name`). Hard problems force a rewrite whatever the critic says; soft ones (repeated title, repeated phrase) go to the critic and the report;
   - *critic* (separate route): 13 criteria, each with a reason and a **verbatim quote** as evidence. Evidence not found in the script caps the score at 5 and blocks "ship"; skipped criteria count as 0;
   - *rewrite*: bounded by depth (`fast` = 1 round, `premium` = 2 via `CREATIVE_SCRIPT_DEPTH`); the critic may demand a new angle/structure/hook/ending; a rewrite that keeps >80 % of the words while the critic asked for substance is rejected;
   - *tighten*: if the script still overruns the video, up to two cut-only passes (no critic call).
   Fast and Premium share every quality rule; depth only changes how many rewrite rounds are allowed.
5. **Storyboard compile** (`creative/production.py`): scene time follows the real length of the spoken line (water-filling allocation); total speech must fit the video. Scenes keep `script_line`, `why_visual`, `emotion`, `focus`, `link_prev`, `reference_trait`.
6. **Approval** (`app/studio_orchestrator.py`): the chat shows what was understood, the chosen idea and why, how the script was reached (critic evidence, timing, unresolved objections and why the loop stopped) and every scene.
7. **After TTS**: real audio is compared with the estimate; narration longer than the plan raises a warning (`brain/content_creator.py::_check_narration_timing`).
8. **After render**: `creative/fidelity.py` compares the output file with the reference profile (cut rate, colours, vision judgement). A clear mismatch sets the review to `needs_attention`; nothing is regenerated without the user.

## Reference analysis (`creative/reference.py`)

A reference video (attachment, or a social link fetched through the relay) is analysed for real, frame by frame (a table picture and a per-frame text list are posted in the chat): ffmpeg scene detection (shot lengths, cuts per second), dominant colours from sampled frames, and a vision description of typography, composition, motion language, transitions, density, hook and narrative. Sound is only measured. If the link cannot be fetched (Instagram/TikTok normally need a login, and `yt-dlp` is not installed on the server) the profile is `unavailable` with a reason, the user is told to upload the file, and the approval message states that the reference was **not** followed. A default style is never substituted silently.

## Not done / limits

- Social links are fetched by the Vercel relay (`deploy/social-relay`, yt-dlp inside). TikTok works as is; YouTube, Vimeo and Instagram need a logged-in cookie session on the relay (see its README); without one the user is asked to upload the file.
- The vision description depends on the provider; when it times out the profile holds only measured pacing and colour and says so.
- Choosing another angle or hook from the approval message is not a one-click action yet: edits go through the scene editor or the chat revision flow.
- Rendering a *draft preview* before the final render (spec step 9–11) is not added; fidelity runs on the finished candidate output.

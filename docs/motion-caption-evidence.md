# Speech-timed product captions: branch evidence

Date: 2026-10-28. Base: PR #4, `motion-contract-repairs` at
`54993cb43b1f2808e2988be4754b3e72371d049d`, still open when this work began.
This branch does not merge/rebase/cherry-pick the 13 local-only main commits.
The untracked `.agents/skills/`, benchmark directory and raw media are preserved.

## Local-only reference comparison

Files were read with `git show <commit>:<path>`; untracked agent rules were read
in place. Status refers to use on this branch, not the quality of earlier work.

| Reference file(s) | Status | Why / disposition |
| --- | --- | --- |
| `2258584:.claude/skills/ai-render-motion/SKILL.md` | needs rewrite | Persian, template-only and review principles remain useful. The document assumes a Jarvis motion client/digest, three beat types, a 0.9 s minimum, strict claim/word grounding, old quality helpers and untracked tests. Those are not this branch's runtime. Rewritten at the same committed location. |
| `2258584:.claude/skills/hyperframes*/` and related workflow trees | needs rewrite | General paused-timeline/RTL technique is useful, but routers authorize free HTML authoring, workflow installs and automatic upgrades. Those conflict with maintained templates and pinned 0.8.161. Not imported. |
| `2258584:.claude/skills/remotion-*/` | needs rewrite | Generic React/frame-driven technique remains useful; the router targets 4.0.537, while this branch pins 4.0.536, and free composition creation is outside the product contract. Not imported as executable agent guidance. |
| `2258584:engine/hyperframes/skill_digest.md` | obsolete | No model call on this branch reads it. Its three-type/strict-grounding assumptions also differ from current templates. Not added; a replacement is pending an actual typed planner consumer. |
| `b833c98:brain/motion_llm.py` | obsolete | Local-only Jarvis JSON client is absent upstream. It does not itself load the digest. This branch's existing planners use the maintained gateway/client paths; copying this file would neither route their calls nor install a digest consumer. Reference only. |
| `260487f:brain/talking_reel_2.py`, `engine/hyperframes/{schema,builder,quality,renderer}.py` | needs rewrite | The local snapshot has strict spoken_phrase/source/claims/mechanism evidence, three supported build types and typography checks. The current schema/catalog is broader, has a 0.65 s minimum and sentence-based continuous beats. Its default-deny full-frame gate uses `allow_full_frame`, not the old evidence fields. No whole-commit import. |
| `260487f:docs/talking2_benchmark/{acceptance_contract,controlled_benchmark_method,score_rubric}.md` | still valid | Separating technical checks from listening, editorial and customer acceptance remains valid methodology. It is comparison guidance, not fresh proof for this branch. Not copied. |
| `260487f:docs/talking2_benchmark/prompt3_*` reports/media/manifests | obsolete | Checkout-specific, partial historic evidence; source/schema/runtime versions differ. Not reused as passing acceptance or copied over the user's untracked benchmark artifacts. |
| Untracked `.agents/skills/ai-render-motion/SKILL.md` | needs rewrite | Same stale client/digest/three-type/grounding claims, plus `.Codex/skills/SOURCES.md` and the claim tests should remain untracked. Read for comparison and preserved unchanged; committed rules live under `.claude/skills/ai-render-motion/`. |

## Implementation and boundaries

New narration can carry ElevenLabs relay character alignment alongside audio;
the original text alignment is preferred over normalized text. Older or
audio-only gateway narration uses the existing Scribe function once, with a
job-local SHA-256 cache. Normalized matching maps measured boundaries back to
script words; the displayed text is never ASR spelling. Substantial drift,
missing/extra content, changed numbers, non-finite/overlapping/out-of-scene
times and unavailable word boundaries become estimated timing.

The HyperFrames page and cinematic DirectedReel now use measured starts for
pages/word colour and measured ends to release the active highlight. Classic
Remotion variants show overlay titles without narration word captions. Both
engines receive the same prepared scene timing in the job, so a browser failure
does not repeat ASR. Any estimated scene sets `caption_timing: "estimated"` in
job state/evidence and holds the candidate before publication.

This change adds no model-authored code, provider substitution, deployment or
chat-motion enablement. No runtime digest was added. To make one useful, a
future typed motion-planner call must read/version a maintained digest, insert
it into its actual prompt and have a test proving that prompt is consumed. The
local-only Jarvis client alone does not do that.

## Verification

The complete suite was run with the existing isolated Python environment and
`DATABASE_URL=` so `.env` does not point tests at a developer database:

```sh
DATABASE_URL= /private/tmp/pr4-review-venv/bin/python -m pytest -q -rs tests
cd web
npm test
npm run build
```

Final verification: **571 passed, 8 skipped**, with 17 new caption-alignment
cases. Frontend: **78 passed**, and `npm run build` passed. Skill frontmatter
validation and `git diff --check` passed. Vite retains its advisory about large
chunks; Python reports existing dependency/deprecation warnings.
The four additional skips versus the stated 558/4 baseline are the
libass-dependent cases on this host (554 existing passes + 17 new passes).
The default host Python could not collect the suite without project dependencies. A prior
run with the checkout database setting failed to connect to local PostgreSQL;
that is not counted as a passing run.

The new mocked tests exercise relay TTS response decoding and sidecar hashing,
script preservation, changed-number rejection, invalid/missing alignment,
same-audio cache reuse across file names, cache invalidation after byte changes,
actual generated page times, app-worker publication/hold and one ASR attempt
across renderer fallback. Existing contract tests cover owned paths, render
budgets, renderer fallback and technical/creative review holds.

## Real two-scene fixture

The fixture uses the installed macOS Majed voice to record five isolated words,
trims silence, and concatenates them with known gaps. These are local fixture
recordings, not production ElevenLabs narration or natural Persian speech.
The existing Scribe function is mocked with the known waveform boundaries;
its real cache and mapping code runs. The identical second scene and a second
preparation use the hash cache: one mocked ASR call, zero live provider calls.
Both pinned browser engines then render actual MP4s with audio.

```sh
DATABASE_URL= \
HYPERFRAMES_CLI=/private/tmp/motion-contract-hf/node_modules/hyperframes/bin/hyperframes.mjs \
HYPERFRAMES_BROWSER_PATH=/Users/amirhossein/.cache/hyperframes/chrome/chrome-headless-shell/mac_arm-152.0.7977.30/chrome-headless-shell-mac-arm64/chrome-headless-shell \
REMOTION_BROWSER_EXECUTABLE=/Users/amirhossein/.cache/hyperframes/chrome/chrome-headless-shell/mac_arm-152.0.7977.30/chrome-headless-shell-mac-arm64/chrome-headless-shell \
HF_TELEMETRY_DISABLED=1 \
/private/tmp/pr4-review-venv/bin/python scripts/product_caption_fixture.py \
  --output /private/tmp/product-caption-fixture \
  --gsap /private/tmp/motion-contract-hf/node_modules/gsap/dist/gsap.min.js
```

Replace machine-specific installed paths on another host. The script's default
GSAP resolver can fetch the pinned, integrity-checked package if `--gsap` is
omitted. No runtime versions were upgraded.

| Actual output | Result |
| --- | --- |
| HyperFrames `product-reel.mp4` | Two 129-frame scenes; 1080×1920; 30/1 fps; H.264/AAC; container duration 8.600 s; full FFmpeg decode passed. |
| Cinematic Remotion `remotion-reel.mp4` | Same 258 video frames, size/fps and codecs; container duration 8.619 s (audio padding); full decode passed. |
| Ordinary word start, both engines | Alignment 0.775208 s; first gold-highlight frame 24 at 0.800000 s; error +24.792 ms (<33.333 ms). Previous frame has zero accent pixels in the caption region. |
| Fifth-word page change in scene two, both engines | Alignment 7.623875 s; first highlight frame 229 at 7.633333 s; error +9.458 ms (<33.333 ms). Previous frame has zero accent pixels. |
| Visual inspection | Decoded previous/onset/next frames inspected for both changes and both engines; Persian captions are RTL and joined, with local Ray. This is a timing/visual fixture check, not full listening/editorial acceptance. |

Committed evidence:
[results and output hashes](motion-caption-fixture/results.json),
[HyperFrames ffprobe](motion-caption-fixture/product-reel-ffprobe.json),
[Remotion ffprobe](motion-caption-fixture/remotion-reel-ffprobe.json), and
[frame sheet](motion-caption-fixture/word-changes.png).
The MP4s remain locally at `/private/tmp/product-caption-fixture/`; regenerate
with the script if those temporary files are removed.

![Decoded frames around two measured word changes](motion-caption-fixture/word-changes.png)

## Direct tests versus app run; pending

These are offline pytest worker calls with mocked providers/QC, frontend tests,
a frontend build, and direct real HyperFrames/Remotion fixture renders. No HTTP
app session, server restart, deployment, live relay/TTS/STT, natural-speech
alignment assessment, or human audio/customer approval was performed.
Production provider response and language quality remain pending.

The default suite skips four libass-dependent cases because the available
FFmpeg lacks its subtitles filter, one MediaPipe case because that optional
package is absent, two opt-in talking_2 render cases and one opt-in TSCaps case.
These skipped checks are not claimed as passes. The product caption fixture
does not replace talking_2's native caption/burn-in acceptance.

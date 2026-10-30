# Motion application acceptance — step 4

Date: 2026-10-30. **Incomplete: setup blocked; no application acceptance jobs have run.**
This draft records the actual preflight and evidence, not direct-render results or simulated job outcomes.

## Baseline and scope

- Fork: `AmirNaderi1997/AI_render_clean-motion-contract-repairs`; remote `fork`; upstream remains read-only.
- Baseline: `1af94b605de3eeea8ad0c0cf1b382be5477025b6` (`fork/main`). PRs #1 and #3 are merged. PR #2 is closed without a merge event, but its commit `6d4071fbd4d4c85ca8983a4be5113a77667d7d9b` is an ancestor of this baseline. All three changes are present.
- Isolated worktree: `/Users/amirhossein/Documents/AI_render-motion-app-acceptance`.
- Motion code is unchanged. This PR contains only this document. Media and diagnostic artifacts remain outside Git.
- Required runtime settings: `TALKING_HYPERFRAMES_ENABLED=true`, `REEL_ENGINE=hyperframes`, `REMOTION_LOOK` unset. These are requirements, **not verified running configuration**: the stack has not started.
- Required stack: backend, worker, PostgreSQL, Redis and served frontend, following README and Compose. No threading-only or direct-render substitute was used.

## Budget and inputs

The user approved an estimated 30–50 provider requests and required a stop before exceeding 60. Actual provider requests initiated for this acceptance: **0**; incurred task provider cost: **0**. No provider health probes or generation retries were sent. Future runs must count provider attempts, including automatic retries and TTS capability fallback, before authorizing additional operations. The estimate is not a hard upper bound on the application's nested retries.

The user explicitly authorized joining the first two existing clips of the same speaker. WEBM was excluded from acceptance input and has not been used for a job.

Evidence root (local, not committed):
`/Users/amirhossein/Documents/motion-app-acceptance-evidence/2026-10-30/`

| Input | SHA-256 |
| --- | --- |
| `/Users/amirhossein/Documents/AI_render_clean/raw/talking2_benchmark/01_choice_and_recommendation.mp4` | `ff3eff62bd00ee32ffa134f4e15634ae4d2369fb6ec260353ab9e679f3eee576` |
| `/Users/amirhossein/Documents/AI_render_clean/raw/talking2_benchmark/02_service_rationale.mp4` | `e5a5a95d74b3ef7c68c9167fd6dcbd43da7f64516dac7fea18d2f1d4d1032d01` |
| `speaker-01-02.mp4` under the evidence root | `e58fa11057d624da1245100eb852fa60991ee82192ca6428cd61b851de86414e` |

Preparation: FFmpeg concat demuxer, first clip then second clip, stream copy and MP4 faststart. Original audio retained. Prepared input is **37.588021 seconds, 1920×1080, 30/1 fps, with audio**. This describes the source, not a rendered acceptance output. The application's output must still be verified as 1080×1920 with the face in the lower half.

Local evidence:

- `speaker-concat.txt`: exact source order.
- `input-manifest.json`: source and prepared hashes plus full input ffprobe JSON.
- `input-1s.jpg`, `input-18s.jpg`, `input-36s.jpg`: inspected source frames show the same speaker. These are input checks, not per-beat output frame sheets or proof of final face placement.
- `docker-preflight.txt`: Docker Desktop status timeout and Docker socket HTTP timeout.

Product inputs remain unresolved. Replies contained placeholders or an illustrative Nike product/path, not actual light/dark product assets and a usable brief. The illustrative `/Users/amirhossein/Desktop/shoe-light.jpg` does not exist. No product identity, specification, photograph or link was invented. A script containing a number and a Latin brand name is still pending the real product brief.

## Setup blocker

After the user reported opening Docker Desktop:

- `docker ps` and `docker info` each timed out after 15 seconds.
- `docker desktop status` timed out after 10 seconds.
- `curl --max-time 5 --unix-socket ~/.docker/run/docker.sock http://localhost/_ping` exited 28 after about 5 seconds, receiving zero bytes.
- Docker backend processes and the Unix socket exist, but neither proves engine readiness.
- Attempting to inspect the Docker Desktop window through computer use also timed out.

The app was not started against a different runtime, and existing Docker data was not reset or deleted. Docker engine recovery is needed before acceptance can proceed. This is an environment blocker, not evidence of a motion-code defect.

## Example 1 — talking_2 kinetic-text beat

| Result | Job/status | Evidence and reason |
| --- | --- | --- |
| **Blocked / not run** | No job ID; no application status | Docker unavailable. Speaker input prepared as above. No UI submission, approved plan, renderer, output hash, output ffprobe, technical QC, motion/DOM QC, caption timing, output frame sheet, or final-status screenshot exists. |

## Example 2 — two-item comparison

| Result | Job/status | Evidence and reason |
| --- | --- | --- |
| **Blocked / not run** | No job ID; no application status | Docker unavailable. talking_2 or talking_5 selection and the actual two-item plan remain pending. No planner result or UI storyboard edit has occurred; all downstream acceptance evidence is unavailable. |

## Example 3 — step-by-step beat

| Result | Job/status | Evidence and reason |
| --- | --- | --- |
| **Blocked / not run** | No job ID; no application status | Docker unavailable. Required steps beat has not been planned or approved in the UI. All downstream acceptance evidence is unavailable. |

## Example 4 — Content Creator HyperFrames product hero

| Result | Job/status | Evidence and reason |
| --- | --- | --- |
| **Blocked / not run** | No job ID; no application status | Docker unavailable and actual product photographs/brief absent. No storyboard, generation, render or QC has occurred. |

## Example 5 — narrated multi-scene product promo

| Variant | Result | Job/status | Evidence and reason |
| --- | --- | --- | --- |
| 5a: HyperFrames | **Blocked / not run** | No job ID; no application status | Docker unavailable and actual product inputs absent. No narration generated. |
| 5b: forced HyperFrames failure → classic Remotion | **Blocked / not run** | No job ID; no application status | Same blockers. No failure was injected and no fallback/review hold has been observed. Runtime-only failure injection and UI rerender/cache reuse must be checked before execution; no job-file edits are authorized. |

## Review, failures and follow-up

No example is passed, held by the application, or proven failed in the application. In particular, **blocked is not `needs_review` or `error`**. There is no export to listen to, no caption synchronization judgment and no output visual acceptance claim.

When execution is unblocked, preserve each approved plan/storyboard JSON and capture every beat/scene at start, middle and end plus every transition midpoint. Inspect face clearance, clipping, joined RTL Persian, Persian display digits and product cropping. Listen to complete narrated exports and record visibly early/late captions. Record technical and DOM/motion QC, `caption_timing.json`, renderer evidence, hashes and UI status screenshots. Any unavailable evidence must remain explicitly unavailable.

No provider failure was observed because no request was made. No motion-code fix is established by this preflight. Do not infer a code patch from Docker unavailability or missing inputs. Any future code-fix finding must name the source file, the failing application job and evidence, and a suggested fix; fixes belong in a separate follow-up.

Resume after Docker API responds and real product inputs are supplied. Keep this PR draft until the five examples (including both example-5 variants) have actual application evidence or explicitly documented per-example execution failures.

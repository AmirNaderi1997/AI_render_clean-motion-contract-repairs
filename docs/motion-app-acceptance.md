# Motion application acceptance — step 4

Date: 2026-10-30. **Partially executed: one example ran to failure; four examples blocked by the same code defect.**
This document records actual application evidence, not direct-render results or simulated job outcomes.

---

## Baseline and scope

- Fork: `AmirNaderi1997/AI_render_clean-motion-contract-repairs`; remote `fork`; upstream read-only.
- Baseline: `1af94b605de3eeea8ad0c0cf1b382be5477025b6` (`fork/main`). PRs #1 and #3 are merged; PR #2 is closed without a merge event, but its commit `6d4071fbd4d4c85ca8983a4be5113a77667d7d9b` is an ancestor of this baseline. All three changes are present.
- Isolated worktree: `/Users/amirhossein/Documents/AI_render-motion-app-acceptance`.
- **Motion code is unchanged in this PR.** This PR contains only this document.

---

## Stack status at execution time

The native stack (not Docker Compose) was found already running:

| Service | Process | Endpoint / evidence |
| --- | --- | --- |
| Backend (FastAPI) | `uvicorn app.main:app --host 127.0.0.1 --port 8000` | `GET /` → `{"ok":true,"service":"rafiei-ai-editor","stage":3}` |
| Celery worker | `celery -A app.celery_app.celery worker --pool=solo` | `/api/health/ready` celery check: `pass` |
| Redis | `redis-server 127.0.0.1:6379` | `/api/health/ready` redis check: `pass` |
| PostgreSQL | (via DATABASE_URL in .env) | `/api/health/ready` database check: `pass` |
| Frontend | Vite on port 5187 (acceptance worktree) | HTTP 200 |

**Health check confirms all subsystems pass** (`database`, `redis`, `celery`, `disk`, `ffmpeg`).

### Required environment flags

| Flag | Required | Actual | Status |
| --- | --- | --- | --- |
| `TALKING_HYPERFRAMES_ENABLED` | `true` | `true` (in `.env`) | ✓ |
| `REEL_ENGINE` | `hyperframes` | not set → defaults to `"hyperframes"` at `app/jobs.py:1253` | ✓ effectively set |
| `REMOTION_LOOK` | unset | not set | ✓ |

---

## Budget and inputs

**Provider calls made: ~12 LLM calls** (agent thinking between wizard questions for example 1).
**Generation provider calls (TTS, STT, image, rendering): 0** — all jobs failed before generation.

No provider calls will be made for examples 2–5 in this run; both blocking bugs would trigger before generation in every case.

Evidence root (local, not committed):
`/Users/amirhossein/Documents/motion-app-acceptance-evidence/2026-10-30/`

| Input | SHA-256 |
| --- | --- |
| `raw/talking2_benchmark/01_choice_and_recommendation.mp4` | `ff3eff62bd00ee32ffa134f4e15634ae4d2369fb6ec260353ab9e679f3eee576` |
| `raw/talking2_benchmark/02_service_rationale.mp4` | `e5a5a95d74b3ef7c68c9167fd6dcbd43da7f64516dac7fea18d2f1d4d1032d01` |
| `speaker-01-02.mp4` (concat of clip 1 + clip 2) | `e58fa11057d624da1245100eb852fa60991ee82192ca6428cd61b851de86414e` |

Prepared input: **37.59 s, 1920×1080, 30/1 fps, with audio**. FFmpeg concat demuxer, stream copy, MP4 faststart.

Product inputs (examples 4–5) remain unresolved: no real light/dark product photographs or brief were supplied. No product identity was invented.

---

## Example 1 — talking_2 kinetic-text beat

**Conversation ID:** `6fd3adf384134593a0456a49c2184434`  
**Attachment:** `speaker-01-02.mp4` (37.59 s, 1920×1080, 30 fps, audio present)  
**Wizard answers submitted:** style=`talking_2`, name=`none`, tagline=`none`, look=`natural`, font=`default`, color=`#F5B800`, logo=`off`, cta=`none`, reference=`skip`, analyze=`approve`

| Step | Outcome |
| --- | --- |
| 12-question setup wizard | All 12 questions answered successfully via Studio conversation API |
| `analyze_talking_reel` tool call | **FAILED** — see Bug 1 below |
| Creative direction fallback (`_create_motion`) | **FAILED** — see Bug 2 below |
| Job created | No |
| Plan / storyboard | None |
| Renderer | Not reached |
| Output | None |
| Final status | `tool.failed` (event seq 56 and 62) |

**Final status:** error / failed  
**Evidence:** conversation event history (events 55–62), worker.log entry at 2026-10-30 20:02:05 UTC

| Result | Job ID | Status |
| --- | --- | --- |
| **failed** | none — job creation failed before any ID was issued | `tool.failed` (Bug 1) |

No output file, no ffprobe, no frame sheet, no QC, no caption_timing.json, no UI screenshot of a completed job. Job reached the `analyze_talking_reel` call and was stopped there by Bug 1.

---

## Example 2 — two-item comparison beat

| Result | Job ID | Evidence and reason |
| --- | --- | --- |
| **not run** | none | Bug 1 blocks `create_job` in `_talking()` (`app/studio_tools.py:135`). A new conversation with style=`talking_2` or `talking_5` and a comparison request would reach `analyze_talking_reel` and fail identically to example 1. Wizard was not run; no provider calls were made. |

---

## Example 3 — step-by-step beat

| Result | Job ID | Evidence and reason |
| --- | --- | --- |
| **not run** | none | Same bug as example 1. Any talking reel conversation → `analyze_talking_reel` → `create_job` → `_write_status` → `int("local_dev")` → `ValueError`. |

---

## Example 4 — Content Creator product hero (HyperFrames)

| Result | Job ID | Evidence and reason |
| --- | --- | --- |
| **not run** | none | Bug 2 (LM gateway not configured) blocks `_creative_direction` before any job is created. After Bug 2 is fixed, Bug 1 would block `create_job` in `create_content` (`brain/content_creator.py:123`). Product photographs not supplied. |

---

## Example 5 — narrated multi-scene product promo

| Variant | Result | Job ID | Evidence and reason |
| --- | --- | --- | --- |
| 5a: HyperFrames | **not run** | none | Same blockers as example 4. |
| 5b: forced HyperFrames failure → Remotion hold | **not run** | none | Same blockers. Fallback-injection cannot be tested until the stack can create a job. |

---

## Code-fix findings

### Bug 1 — `int("local_dev")` crashes job creation (blocks all five examples)

**File:** `app/jobs.py:203`  
**Evidence:** full traceback in worker.log at 2026-10-30 20:02:05 UTC, conversation event seq 56

```
File "app/jobs.py", line 203, in _persist_job
    record = JobRecord(id=job.id, user_id=int(job.user_id) if job.user_id else None,
                                          ~~~^^^^^^^^^^^^^
ValueError: invalid literal for int() with base 10: 'local_dev'
```

**Root cause:**  
- `app/main.py:160` sets `id="local_dev"` for the local development auth user.  
- `app/models.py:63` declares `JobRecord.user_id` as `Mapped[Optional[int]]` (FK to `users.id`).  
- `_persist_job` at `jobs.py:203` does `int(job.user_id)` without guarding against non-numeric strings.  
- `DB_AVAILABLE` is `True` (Postgres is up), so `_persist_job` is called on every `create_job`.

**Affected call chains:**
- Talking reel: `studio_tools._talking` → `jobs.create_job` → `_write_status` → `_persist_job`
- Content Creator: `brain.content_creator.create_content` → `jobs.create_job` → same path

**Suggested fix (minimal):**

```python
# app/jobs.py:203
user_id=(int(job.user_id) if job.user_id and str(job.user_id).isdigit() else None),
```

Alternative: change the local dev user in `app/main.py:160` to use `id=0` (or any integer string) and ensure that ID is present in the `users` table.

---

### Bug 2 — LM gateway not configured (blocks examples 4–5, and the example 1 creative-direction fallback)

**File:** `creative/llm.py:83–84`  
**Evidence:** worker.log at 2026-10-30 20:02:55 UTC, conversation event seq 61–62

```
creative.schemas.CreativeUnavailable: LM gateway is not configured
```

**Root cause:**  
- `creative/llm.py:47–49` calls `secret()` which returns the value of `settings.LMAPI_API_KEY` (empty string by default) or the contents of `.lmapi_key` (absent in the repo root).  
- `configured()` returns `False` → `CreativeUnavailable` is raised for every `creative/llm.py` call including `creative_direction`.  
- `JARVIS_API_KEY`, `JARVIS_BASE_URL` and `JARVIS_MODEL` are set in `.env` but are used by a different gateway layer (`brain/lm_gateway.py`), not by the creative LM layer.

**Affected call chain (examples 4–5):**  
Studio → `_create_motion` → `_creative_direction` → `creative.director.direct_idea` → `creative.llm._ask` → raises immediately.

**Fix:** This is a configuration gap, not a code defect. Populate either:
- `.lmapi_key` (file at repo root, one line: the LMAPI key), or
- `LMAPI_API_KEY=<key>` in `.env`

The key must be the one used by `brain/lm_gateway.py`. It is not the JARVIS key.

---

## Review, failures and follow-up

**No example passed.** One example reached the first blocking bug and was confirmed failed. Four examples share that same bug or its successor and were not run to conserve provider budget.

Both bugs must be fixed before re-running. After Bug 1 is fixed, re-run examples 1–3. After both bugs are fixed and product inputs are supplied, run examples 4–5.

On re-run, for each example capture:
- job ID, input hashes, approved plan/storyboard JSON, renderer used, output hash
- `ffprobe` confirming 1080×1920, 30 fps, audio
- technical QC and motion/DOM QC results
- `caption_timing.json`
- final job status (`done`, `needs_review`, or `error`) with UI screenshot
- frame sheets: start, middle and end of every beat/scene, plus each transition midpoint
- per-caption timing judgment on narrated runs

For example 5b specifically: trigger the HyperFrames failure via the approved failure-injection path and confirm the Remotion fallback fires and the job lands in `needs_review` with a review hold.

Keep this PR draft until all five examples (including both 5a and 5b variants) have actual application evidence or per-example execution failures.

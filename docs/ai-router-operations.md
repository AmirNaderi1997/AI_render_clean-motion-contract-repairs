# AI router — operator guide

## Architecture and scope

There is no remote LM API (the former `lmapi.rafiei.co` gateway, its `.lmapi_key`, `LMAPI_*` settings and media-policy patch were removed). The existing FastAPI/SQLAlchemy/Celery and React/Vite stack is preserved. `brain/lm_gateway.py` is still the request/routing boundary every intelligence caller uses: routes, their model order, bounded concurrency, the audit log and the admin panel live there. Each request is sent straight to a provider by `brain/lm_direct.py`; `brain/lm_adapters.py` owns the OpenAI-compatible payload shape. `brain/llm.py`, `brain/ai_provider.py` and the Studio agents keep their call contracts.

Served by the router: chat, edit planning, subtitle translation/correction, scripts, effect selection, image/video-frame understanding, visual QC, structured JSON and streaming. Without a usable provider key, `configured()` is false and callers use their legacy Arvan path where they have one.

Specialist paths:

- Images: Arvan image adapter (`brain/media_provider.py`).
- Narration/TTS: direct Jarvis Eleven v3 → Sarovi Eleven v4 through `brain/lm_direct.py`, with Persian casting in `brain/speech_policy.py`. An explicitly configured ElevenLabs relay retains its existing path.
- Transcription: own ElevenLabs Scribe relay (only when configured) → Sarovi Whisper → local Whisper (`brain/transcribe.py`). Hosted results require valid word timestamps; Arvan transcription is never used.
- Music and video rendering: existing engines/library operations.

## How a request is routed

1. The route's model list is read on every request (no deploy needed after a change). Each entry `custom:<model>#<group>` maps to a provider: `jarvis-all-models` → Jarvis, `sarovi-all-models` → Sarovi, `arvancloud-all-models` → ArvanCloud, `openai-all-models` → OpenAI; `google:<model>` → Gemini.
2. Pairs whose provider is disabled or has no key are skipped. Then, unless the route turns automatic fallback off, each enabled provider's default model is appended (Jarvis `CLAUDE_SONNET_5_5`, Sarovi `gpt-4.1-mini`).
3. Pairs are tried in order, once each, within `min(300, 2 × route timeout)` seconds. Structured callers' validators run on each answer; an answer that does not validate counts as a failure and the next pair is asked.
4. Streaming (`stream_chat`) starts the first pair at once and hedges the next one after 2.5 s without text; the first provider to speak wins and is never spliced with another. If no stream yields text, the same route is asked once for a bounded non-streamed answer.
5. A provider that answers 401/403 is skipped for 10 minutes, 402 (no credit) for 2 minutes.

## Setup and deployment

1. Give the server at least one provider key, backend only:
   - `.env`: `DIRECT_JARVIS_API_KEY=` and/or `DIRECT_SAROVI_API_KEY=` (`JARVIS_API_KEY` / `SAROVI_API_KEY` also work; `JARVIS_BASE_URL`, `JARVIS_MODEL`, `SAROVI_BASE_URL`, `SAROVI_LLM_MODEL` set defaults below admin-saved values), or
   - *Settings → AI Models & Logs → Direct providers*: paste the key (write-only, stored in `$JOBS_DIR/ai_gateway/direct_keys.json`, mode 0600) and press **Test**.
2. Jarvis and Sarovi are on by default. ArvanCloud, OpenAI and Gemini are off by default even when `ARVAN_AI_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY` exist; switch them on in the same tab to use them as further text providers.
3. Apply `alembic upgrade head`. The existing gateway tables (models, routes, settings, audit logs) are reused; nothing new is added.
4. Grant operators only via server `AI_ADMIN_USER_IDS` or `AI_ADMIN_EMAILS`, comma separated. Production checks the authenticated user, never a browser-supplied role.
5. Optional: *Models → Register task models* re-registers the task table's provider models as Untested; *Run test* sends one small request (chat, vision, structured, tools or streaming) through the router and records the result. Saving a route still requires the capability its endpoint needs to have passed a test.

The VPS Compose overlay no longer mounts any LM credential. `.motion_key` is unrelated (Motion.so) and still required by that overlay.

## Safety, observability and limits

- Provider base URLs must be public HTTPS hosts without credentials or query. Redirects are not followed. Model names are passed verbatim.
- Default concurrency is four model calls per backend worker, not a distributed budget.
- No model code or model-proposed endpoint is executed. Structured plans are parsed and validated before invoking existing tools.
- Request bodies, media and key-bearing text are redacted and bounded in logs (all direct provider keys, Arvan and ElevenLabs keys). Admin settings can disable request/response capture. Logs keep provider, actual model when reported, usage when reported, correlation/job/conversation/user IDs and the per-pair attempt trail.
- Analytics is limited to the newest 50,000 matching requests; CSV exports to 10,000 and escape formula cells. Logs are not deleted automatically.

## Narration and transcription

Audio shares direct-provider keys, effective base URLs, master/provider switches and the existing gateway audit store. It does **not** use chat models, chat hedging, automatic retries or the removed LMAPI transport. Every outgoing audio attempt records route `narration` or `transcription`, provider, model, latency, HTTP status and success/failure. Audio bytes, transcript text, synthesis input, credentials and provider error bodies are omitted even when chat message capture is enabled. A rejected timestamp response is recorded as failed capability validation with its actual HTTP 200 status.

### Narration

With an empty `ELEVENLABS_PROXY_URL`, `NARRATION_TTS_ORDER` defaults to:

```dotenv
NARRATION_TTS_ORDER=sarovi:elevenlabs/eleven-v4,jarvis:TTS_ELEVEN_V3
```

Sarovi Eleven v4 with `george` is the chosen primary narration voice after listening to both samples; Jarvis Eleven v3 remains the fallback. Only these two reseller providers are supported. The first usable model for each provider reserves its slot; duplicate provider entries cannot cause another request. One POST per provider, in order, stopping at the first valid audio response. A timeout, ambiguous disconnect or 5xx advances to the next provider and never resubmits to the same provider. Requests have bounded connect/read timeouts, do not follow redirects and do not use SDK retries. Audio must have an `audio/*` media type and be between 1 KiB and 50 MiB; the existing narration caller additionally checks playable duration.

- **Jarvis:** OpenAI-compatible `POST {base}/audio/speech`, `model`, `input`, `voice`, `response_format=mp3`, and `language_code` when known. The existing ElevenLabs voice ID is preserved: operator-reviewed Persian casting catalog, `PERSIAN_ELEVENLABS_VOICE_ID` preference, caller/Localize voice, then `ELEVENLABS_VOICE_ID`. Without a relay, voice discovery never calls ElevenLabs; an absent catalog uses the configured voice ID. Jarvis's public guide does not document a voice-list endpoint; the live probe is the evidence for the configured ID.
- **Sarovi:** its live `/v1/models` metadata and [model documentation](https://api.sarovi.ir/developers/models/elevenlabs~eleven-v4) publish `POST {base}/studio/audio`, **not** `/audio/speech`. It accepts `model`, `text`, `voice`, `format=mp3` and returns JSON `output.data` (Base64) plus `output.mediaType`; decoded bytes undergo the same audio validation. It exposes 21 named voices, not arbitrary ElevenLabs IDs. `SAROVI_ELEVENLABS_VOICE=george` is the default; allowed names are george, sarah, adam, alice, bella, bill, brian, callum, charlie, chris, daniel, eric, harry, jessica, laura, liam, lily, matilda, river, roger, will. The model does not accept separate tone instructions.

Persian is restricted to Jarvis `TTS_ELEVEN_V3` and Sarovi `elevenlabs/eleven-v4`. Sarovi Eleven v4 was verified live to speak Persian. Multilingual v2, Flash and Turbo v2.x are never eligible for Persian. No unverified v4/turbo aliases are inferred from a model name.

Neither direct reseller contract promises character timestamps. Even when the caller requests timestamps, direct narration makes one plain synthesis and uses the existing hash-cached STT caption alignment path (relay/Sarovi/local as configured). Script words remain protected; absent or mismatched timing remains review-only. With a nonempty `ELEVENLABS_PROXY_URL`, the existing relay synthesis, casting and unsupported-timestamps plain fallback are preserved.

The installation's older `SAROVI_TTS_MODEL=google/gemini-3.8-flash-tts`, `SAROVI_TTS_VOICE` and `SAROVI_TTS_INSTRUCTIONS` do **not** change this default. For non-Persian audio an operator can explicitly put `sarovi:google/gemini-3.8-flash-tts` in `NARRATION_TTS_ORDER`; only that explicit Google route reads the old voice/instructions settings. Persian Google synthesis remains outside this verified ElevenLabs allow-list.

### Transcription

```dotenv
# Enable only once Sarovi returns word timestamps.
SAROVI_STT_ENABLED=false
SAROVI_STT_MODEL=openai/whisper-large-v3
```

The default transcription chain is an own ElevenLabs relay (only with `ELEVENLABS_PROXY_URL`) → local Whisper. Sarovi STT is disabled by default because its current responses lack word timestamps; hosted calls would be paid and then discarded. Enable it only once Sarovi returns word timestamps. `ASR_ENGINE=whisper` or an explicit `engine=whisper` keeps the local-only choice. `SAROVI_STT_ENABLED=true` explicitly inserts Sarovi between the relay and local Whisper. Local Whisper retains the existing admin STT enable/model/quality-review settings and `WHISPER_ENABLED` behavior. Arvan is excluded because prior testing dropped speech.

The compatible transport sends multipart `POST {base}/audio/transcriptions` with `model`, `file`, optional `language`, `response_format=verbose_json` and `timestamp_granularities[]=word`. **Sarovi's current documented wire contract differs:** its [audio guide](https://api.sarovi.ir/developers/docs/audio) and OpenAPI schema require JSON `audioBase64`/`mediaType`; that mapping is the default (`SAROVI_STT_FORMAT=json`). Both response/timestamp options are requested there too, but the current public schema promises only text, so a successful HTTP response may still fall back locally. `SAROVI_STT_FORMAT=multipart` explicitly selects the compatible transport for a deployment that supports it. There is no automatic second-format POST.

Only nonempty, finite word timings are accepted (top-level words or words nested in segments). Segment-only timing and text-only responses are rejected. Results map to the established `{words:[{w,start,end,prob}],sentences,language,duration,...}` format with engine `sarovi_whisper`; this engine is eligible for the existing transcript cache. Each chain writes `asr_attempts.json` and `asr_cost.json`; reseller cost is `null` unless a reliable price is known, never the ElevenLabs Scribe tariff. All paths remove temporary extracted audio. No new database migration is needed.

### Bounded live verification, 2026-10-31

Exactly two TTS POSTs and two STT POSTs were submitted; no acceptance examples were run. Audio and the persistent probe ledger are outside Git under `/private/tmp/ai-render-audio-live-20261031/` on the development Mac.

| Call | Model / wire | Latency | Result |
| --- | --- | --- | --- |
| Jarvis TTS | `TTS_ELEVEN_V3`, configured ElevenLabs ID | 8,851 ms including local probe/write | `audio/mpeg`, 44,348 bytes, 2.768938 s |
| Sarovi TTS | `elevenlabs/eleven-v4`, `george` | 3,055 ms including local probe/write | `audio/mpeg`, 44,764 bytes, 2.720000 s |
| Sarovi STT, Jarvis clip | `openai/whisper-large-v3`, JSON/Base64 | 4,737 ms | HTTP 200, Persian text, **no word timestamps**; correctly rejected for alignment |
| Sarovi STT, Sarovi clip | `openai/whisper-large-v3`, multipart | 993 ms | HTTP 400; no transcript/timestamps |

The JSON transcription recognized the fixed Persian phrase with spelling errors. This confirms Persian speech from Jarvis but is not an ear-quality score. Sarovi's v4 returned playable Persian audio; the user subsequently listened to both samples and chose Sarovi `george` as the primary voice. The current Sarovi API cannot yet be relied on for word alignment: Sarovi STT is therefore disabled by default, and transcription goes directly to local Whisper after the optional own relay until the reseller supplies word timings. Do not substitute invented timing or repeat a billed request to obtain a different response shape. No further paid checks were made.

Offline verification on the same checkout: baseline `752 passed, 10 skipped`; after the change `778 passed, 10 skipped` with `DATABASE_URL= REDIS_URL= python -m pytest -q tests` (the installed `/private/tmp/pr4-review-venv` interpreter). The previously reported environmental failures did not reproduce in that environment. Mocked tests cover provider ordering, one-attempt behavior on timeout/5xx, Persian guards, actual HTTP request formats, missing/invalid word times, relay preservation, caches/local fallback, and secret-free error/audit output.

### Persian Gemini transcription with offline alignment

Set `SAROVI_TRANSCRIBE_ENABLED=true` and
`SAROVI_TRANSCRIBE_MODEL=google/gemini-4-argon`. The default when the enable
variable is absent is disabled, allowing a controlled rollout. The chain is
configured own ElevenLabs relay, Gemini plus MMS, then local Whisper. Explicit
Whisper selection remains local. Accepted results use engine `gemini_aligned`.

Provision `model_quantized.onnx` and `vocab.json` from
`onnx-community/mms-300m-1130-forced-aligner-ONNX`, pinned revision
`2100fb247d8e43962eef24491597fbeb8b469531`, into each app/worker mounted cache at
`/root/.cache/mms-align` (override `MMS_ALIGN_CACHE_DIR`). Download once through
the existing sing-box proxy; never download models during requests. Model SHA256:
`dc79e3bd48bffa9b4fb850d6195710d4eeb13e2fdf1f521eccbca512ab530254`.
Missing files cause an explicit `aligner_cache_missing` fallback. Provision the
small Whisper model under `WHISPER_LOCAL_MODELS_DIR` for the offline reference.
The image installs pinned uroman/regex; it does not use cache-installed Python packages.

MMS uses CPU ONNX Runtime, blank ID 0, and 15-second inference windows. The
quantized model occupies 303 MiB outside the image. The 60.5-second Persian
preflight took 30.14 seconds with 995.6 MiB peak process RSS; this is a probe,
not a production concurrency guarantee. No torch dependency is added. The
Viterbi allocation is capped at 100 million cells. Audio longer than five
minutes is cut at detected silence midpoints, with no chunk exceeding five
minutes. Continuous speech without a safe cut falls back locally.

Safety gates require Persian-script text, at least 90% word placement, finite
monotonic in-range timings no longer than three seconds, rough per-minute
Whisper word-count agreement, and no uncovered speech interval over five
seconds. Arabic-script detection alone cannot distinguish every language;
the source and Whisper reference are explicitly Persian. Pauses alone are not
speech gaps. Rejection codes appear in `asr_attempts.json`. Successful hosted
chunk responses are retained in the job's private transcript archive to avoid
paying again after a later alignment failure. Costs remain in
`asr_gemini_cost.json` and `asr_cost.json`, including rejected hosted results.

Run `DATABASE_URL= REDIS_URL= python -m pytest -q tests`. The real alignment
integration test is opt-in through `MMS_ALIGNMENT_TEST_AUDIO`,
`MMS_ALIGNMENT_TEST_TEXT`, and `MMS_ALIGN_CACHE_DIR`; no large fixture is committed.

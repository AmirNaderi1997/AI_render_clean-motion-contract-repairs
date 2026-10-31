# AI router — operator guide

## Architecture and scope

There is no remote LM API (the former `lmapi.rafiei.co` gateway, its `.lmapi_key`, `LMAPI_*` settings and media-policy patch were removed). The existing FastAPI/SQLAlchemy/Celery and React/Vite stack is preserved. `brain/lm_gateway.py` is still the request/routing boundary every intelligence caller uses: routes, their model order, bounded concurrency, the audit log and the admin panel live there. Each request is sent straight to a provider by `brain/lm_direct.py`; `brain/lm_adapters.py` owns the OpenAI-compatible payload shape. `brain/llm.py`, `brain/ai_provider.py` and the Studio agents keep their call contracts.

Served by the router: chat, edit planning, subtitle translation/correction, scripts, effect selection, image/video-frame understanding, visual QC, structured JSON and streaming. Without a usable provider key, `configured()` is false and callers use their legacy Arvan path where they have one.

Not served by the router (specialist providers, unchanged code paths):

- Images: Arvan image adapter (`brain/media_provider.py`).
- Narration/TTS: ElevenLabs through the Vercel relay (`brain/tts.py`), with the Persian `eleven_v3` casting rules in `brain/speech_policy.py`.
- Transcription: own ElevenLabs Scribe relay, then local Whisper (`brain/transcribe.py`).
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

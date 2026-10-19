# Rafiei LM API — operator guide

## Architecture and scope

The existing FastAPI/SQLAlchemy/Celery and React/Vite stack is preserved. `brain/lm_gateway.py` is the request/routing boundary; `brain/lm_adapters.py` owns protocol differences. `brain/llm.py` and the existing intelligence provider retain their call contracts. Studio classifies requests through the editing-agent route, validates the enum with Pydantic, then runs the existing allowlisted tools and existing plan/storyboard validation. Rendering, job progress, SSE, media ownership, previews, downloads and versions are not replaced.

Text/chat, edit planning, subtitle translation/correction, scripts, effect selection, image/video-frame understanding and visual QC use LM API when its credential is configured. A configured but unavailable LM API fails visibly; it does not silently call another direct text provider.

Specialist image generation remains on the existing Arvan adapter; speech/timestamps remain ElevenLabs through Vercel; transcription remains ElevenLabs/local Whisper. Their LM equivalents appear in the live OpenAPI, but a successful media generation/quality test has not been run, so the editor does not activate unverified adapters. Preserved image/TTS calls are audited with `transport=preserved-specialist`, not falsely labeled LM API. Music and actual video rendering remain existing engines/library operations. There was no existing vector-memory consumer to migrate; the embeddings service/route is available without inventing a memory feature.

## Setup and deployment

1. Install the supplied RTF/plain credential privately: `python scripts/configure_lmapi.py /path/to/credential.rtf`. This creates `.lmapi_key` with mode 0600; Git and Docker context ignore it. Alternatively set backend-only `LMAPI_API_KEY`.
2. `LMAPI_BASE_URL=https://lmapi.rafiei.co/v1`. `LMAPI_API_KEY_FILE` defaults to `.lmapi_key` locally. The VPS Compose overlay binds it read-only at `/run/secrets/lmapi_key`; provision the file before starting that overlay. No credential is baked into an image or returned by an endpoint.
3. Apply `alembic upgrade head` (additive revision `01b9a7d0c123`). No user/job/project table is dropped or changed. Four tables store catalog/health evidence, route configurations, gateway settings and audit logs. Local development follows the existing durable JSON-fallback pattern.
4. Grant the operator only via server `AI_ADMIN_USER_IDS` or `AI_ADMIN_EMAILS`, comma separated. `configure_lmapi.py --admin-user-id ID` can append an operator to the private `.env`. Production checks the existing authenticated user, never a browser-supplied role. The pre-existing loopback development identity can access the local panel.
5. Run `python scripts/bootstrap_lmapi.py --probe --activate`. This runs six small probes, not a media render. It activates only capability-verified text/vision defaults. It never re-runs a user job. Additional model tests are explicit admin actions (eight per operator per minute).
6. Open `/settings/ai` (Settings → AI Models & Logs). Search/test the desired exact ID under Models, then select Routing → a route → add models → drag/drop or arrow buttons → Save. Every new request reads the saved order; no deploy is needed. In-flight requests retain their snapshot.

## Safety, observability and limits

- Only an approved HTTPS host and fixed endpoint allowlist are callable. Redirects are not followed. Model names are passed verbatim; no name-based capability guessing. Catalog declarations are distinguished from real probe evidence, and untested entries remain Untested.
- Default concurrency is four model calls per backend worker, not a distributed global budget. Model requests have bounded timeouts, at most eight candidates, zero default retries, at most two configured retries, and a bounded total deadline. Auto/fusion are never locally retried. 400/401/403/422 do not cause fallback; transient timeouts/429/5xx may select another eligible model. Embeddings never cross model families.
- No model code or model-proposed endpoint is executed. Structured plans are parsed and validated before invoking existing tools. A failed Tool Calling probe never enables that capability for that model.
- Chat streaming can fall back only before emitting any text. An interrupted partial stream is failed and logged, never spliced to another model. Studio continues its existing persisted operational-event stream; partial LLM edit plans are not executed.
- Request bodies/media/key-bearing text are redacted and bounded. Admin settings can disable request/response capture. Logs retain actual HTTP status, model/provider only when reported, usage only when reported, correlation/job/conversation/user IDs when available, retry/fallback trails and errors. Missing cost/tokens remain null. Specialist binary output is omitted. Per-request sampling/truncation is intentional, not a full transcript archive.
- Model statistics cover requested model routes; upstream fallback observations are preserved separately. Analytics is explicitly limited to the newest 50,000 matching retained requests, with a truncation flag; CSV exports require at most 10,000 matching requests and escape formula cells. Logs are not automatically deleted. Plan a retention/backup policy for long-lived installations.
- Models/health evidence share `ai_models`; no duplicate health subsystem was added. Concurrent model probes union verified capabilities under a database row lock.

## Verification record

Live discovery: authenticated model listing (1021 entries at verification), OpenAPI 0.4.1, with exact IDs preserved. Live bounded probes succeeded for Chat, Responses, Anthropic Messages, embeddings (nonempty vectors), vision (blue image semantic check), SSE streaming (actual deltas/completion) and structured JSON. The auto Tool Calling probe returned no tool call and remains unverified. No expensive image/video/speech LM generation probe was performed. Endpoint presence is not claimed as working generation.

Automated verification: gateway retries/fallback/validation/capability gates, live route reload, redaction, log pagination/filtering, admin rejection, adapters, model-case preservation, stream interruption after first token, existing Studio/provider/motion regressions; frontend priority ordering and log query tests; TypeScript/Vite build. See tests for the executable contracts.

Official reference: https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md

# Rafiei LM integration audit and migration

## Existing boundaries

- React/Vite/TypeScript, React Router: `Studio.tsx` is the conversational UI, `api.ts` owns JWT-bearing API calls. `EditorShell` and Settings provide navigation. No admin UI/role exists.
- FastAPI JWT middleware resolves `request.state.user`; loopback development explicitly supplies `local_dev`. Production uses PostgreSQL, async SQLAlchemy, Alembic; Studio has its own durable conversations/projects/actions/events. Local development uses a JSON fallback.
- `brain/llm.py`: JSON text, subtitle correction/translation, effect scoring, vision/QC and asset inspection. `brain/ai_provider.py`: storyboard/planner/talking decisions. `brain/media_provider.py`: image generation and conversion of stills into clips. These are the integration points, not parallel editing systems.
- `brain/tts.py`, Localize narration/timestamps and Scribe use ElevenLabs via the existing Vercel transport. Whisper is the local ASR fallback. Music uses the existing library/upload.
- FastAPI jobs and Celery wrappers execute existing generation/render functions. Remotion/FFmpeg/MLT/HyperFrames remain rendering engines, not LLM providers. Plan/storyboard schemas, tool allowlist, ownership, confirmations, progress, exports and prior versions must remain intact.

## Implementation plan

1. Add gateway model, route, settings and request-log persistence with an additive migration; no changes to existing project tables. Reuse the existing async database/JSON-fallback convention.
2. Add bounded backend-only HTTP adapters for Chat, Responses, Messages, embeddings and verified streaming. Preserve exact model IDs. Capability evidence is recorded independently for each endpoint; names are never capability evidence.
3. Route existing intelligence adapters through the service when LM credentials are configured. Keep specialized media/ElevenLabs fallbacks until LM support is actually verified. Do not reinstall removed legacy providers.
4. Add an admin-only `/admin/ai` API and `/settings/ai` UI with Models, Routing, Logs and Analytics. Use deployment-controlled admin IDs/emails, never client-supplied roles. Store no API keys in API responses or request logs.
5. Validate bounded live API probes, retries/fallback/stream failures, authorization, persistence and Studio regressions; build/typecheck and deploy the validated revision.

## Initial discovery, 2026-10-20

The supplied credential successfully read `/v1/models` (1021 entries) and `/v1/openapi.json` (version 0.4.1). The live spec lists chat, responses, messages, embeddings, image/video generation, speech and transcription paths. Listing a path/model is not execution evidence. No separate model-list attachment was provided, so the authenticated live catalog is the initial reference.

Reference: https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md

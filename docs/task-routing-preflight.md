# Task routing preflight — 2026-10-20

## Google activation and bounded media contract tests

Native `google:gemini-3.5-flash` returned valid JSON with routed-via exactly
`google/gemini-3.5-flash`. No quota API was consulted. Google-first configuration
uses this exact provider pin, followed by independently tested Arvan DeepSeek
and Jarvis Sonnet pairs. The setup script snapshots prior light-route settings.
Vercel was removed from task preferences, scoped model selections and execution.

Media contract probes (one request each, no automatic retry):

- Image: `custom:GPT_IMAGE_2_5_SUNBURST#jarvis-all-models` → HTTP 400, unknown image model.
- Speech: `custom:elevenlabs/eleven-v4#sarovi-all-models` → HTTP 400, unknown audio model.
- Video: `custom:bytedance/seedance-2.5#sarovi-all-models` → HTTP 503, no enabled video providers.

These are pre-generation rejections, not successful media output tests. Upstream
`resolveMediaChain` in `server/src/services/media.ts` matches raw media registry
IDs only, unlike text's group-aware resolver. Exclusive media cutover remains
blocked until the central service has compatible, provider-pinned media routes.
Existing media processing has not been disabled or claimed migrated.

## Deployment gate: pair discovery resolved; media and policy cutover pending

### Correction after authorized browser inspection

The 404 findings below were caused by using normalized public catalog IDs rather
than the raw endpoint registration IDs. They do **not** establish that the deployed
Gateway lacks group routing. The ordinary authenticated Keys UI contains the
requested Jarvis, ArvanCloud, Sarovi, Vercel and OpenAI groups plus native Google.
No Gateway setting or key was changed during inspection.

Bounded synthetic live probes subsequently confirmed:

- `custom:CLAUDE_OPUS_5_5#jarvis-all-models`: HTTP 200, `OK`.
- `custom:CLAUDE_SONNET_5_5#jarvis-all-models`: HTTP 200, valid `{"ok":true}`.
- `custom:DeepSeek-V4-Flash#arvancloud-all-models`: HTTP 200, valid `{"ok":true}`
  with a 120-token budget. An earlier 8-token probe truncated reasoning, and does
  not count as JSON quality evidence.
- `custom:anthropic/claude-sonnet-5.5#vercel-all-models`: HTTP 429 wrapping an
  upstream 403: this model is unavailable on the configured free tier.
- `google:gemini-3.5-flash`: HTTP 502 empty completion with an 8-token budget;
  inconclusive as a quality test, not evidence that Google is generally broken.
- `google:gemini-2.5-flash`: HTTP 404, disabled model.

The quota UI reports no reliable forecasts for any of the seven pools. Do not
claim a verified free balance or remaining Google quota from key health alone.

`brain/lm_tasks.py` now describes 27 task preferences using exact registered raw
IDs. This is staged policy only, not runtime activation. Seven unit cases pass.
There is no discovered Scribe or Arvan embedding pair; their preference lists
remain empty instead of inventing IDs. Costly media probes have not been run.

### Initial evidence (retained for audit)

No production settings or direct-provider connections were changed by this preflight.
The requested exclusive Gateway cutover must not be promoted until provider-scoped
requests and specialized media adapters have been verified end to end.

Authenticated, read-only discovery against `https://lmapi.rafiei.co/v1` returned
1,021 catalog entries and zero `custom:` entries. The advertised OpenAPI contains
chat, responses, messages, embeddings, image generation, video generation, speech
and transcription paths. An advertised path is not proof of media compatibility.

Two bounded chat requests with catalog-derived base IDs returned HTTP 404 with
`code=model_not_found`:

- `custom:deepseek-v4-flash#arvancloud-all-models`
- `custom:anthropicclaude-opus-5.5#jarvis-all-models`

Upstream current source supports group-qualified requests in
`server/src/services/custom-endpoint.ts` and tests them in
`server/src/__tests__/routes/custom-endpoint-groups.test.ts`. The deployed service
does not currently establish that contract. Its version and configured group
membership need inspection via ordinary authorized Gateway administration.
Do not infer a group's actual model IDs from model display names.

## Existing integration points inspected

- `brain/lm_gateway.py`: persistent route order, capability gates, bounded retries,
  audit records, streaming and semantic probes.
- `brain/lm_adapters.py`: chat/responses/messages/embeddings wire adapters;
  specialized media execution deliberately not implemented yet.
- `brain/llm.py`, `brain/ai_provider.py`: central LLM delegation when configured;
  legacy direct Arvan path still exists when not configured.
- `app/studio_orchestrator.py`: intent classification currently shares editing agent.
- `brain/talking_reel.py`: editing agent planning.
- `brain/correct.py`, `brain/localize.py`: correction/translation share subtitles.
- `brain/segment_analysis.py`: segment classification currently shares text route.
- `brain/effect_score_v4.py`, `brain/qc_review.py`, `brain/product_assets.py`:
  distinct vision uses currently share video understanding.
- `brain/tts.py`, `brain/localize.py`: ElevenLabs relay TTS, including Localize's
  timestamped alignment contract, which generic audio output cannot silently replace.
- `brain/transcribe_elevenlabs.py`: Scribe word timestamps and caching.
- `brain/media_provider.py`: direct Arvan image adapter and local fixture adapter.
- `app/routers/lm_admin.py`, `web/src/AIModels.tsx`: existing admin routing UI/API.

## Required next gate

1. Inspect deployed Gateway version and real custom endpoint groups with normal
   admin access; update/configure the Gateway only with explicit scope authorization.
2. Obtain actual execution IDs per group, including independent Google routing.
3. Verify each pair independently; never inherit generic-model probe evidence.
4. Establish reported quota evidence (unknown is not free/unlimited).
5. Implement and verify TTS/STT/image/video adapters, including alignment, durable
   operation IDs and reconciliation after ambiguous network failures.
6. Add task/provider persistence and UI to the existing gateway, map call sites,
   verify fallback/quality/idempotency, then perform exclusive cutover atomically.

No keys, private endpoint credentials, user media or user conversation content are
included in this report or in the two synthetic probes.

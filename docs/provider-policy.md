# Provider routing policy

All hosted text, planning, translation, correction, vision and image-generation requests use the configured Arvan endpoint and its `Authorization: apikey` scheme. No external model fallback is enabled **except the admin-controlled direct fallbacks below**.

- Text: `ARVAN_AI_MODEL` (current installation: GPT-5.6-Sol).
- Vision: `ARVAN_VISION_MODEL` (Gemini-3-Flash-Preview, served by Arvan).
- Images: `ARVAN_IMAGE_MODEL` (Gemini-3.1-Flash-Image-Preview, served by Arvan), chat completions with image/text modalities and validated inline image responses.
- Speech: ElevenLabs only, with Localize's voice/model settings and the mandatory `ELEVENLABS_PROXY_URL` HTTPS relay. Missing relay configuration fails closed; no direct API bypass.
- Transcription: existing ElevenLabs Scribe or local Whisper; no retired hosted transcription fallback.
- Music: existing library and uploaded files. AI music generation is unavailable until a supported Arvan audio-generation contract is configured; the compatibility endpoint returns an actionable error.

Old saved provider names are normalized at execution time, while historical messages and existing rendered files are preserved. Restart the API and workers after deploying; already-running old processes retain their imported code.

Verified against the installation's live model list: text completion, image analysis, inline generated image and a short playable ElevenLabs voice clip through the relay. Unit tests additionally guard against retired provider names in runtime source and silent provider substitution.


## Direct fallbacks (text only)

When LM API fails (timeout, 429/5xx, no usable model), `brain/lm_gateway.py` may answer a **chat** request from a
directly configured provider: Sarovi, Jarvis, ArvanCloud (`aiapi.rafiei.co`, `Authorization: apikey`), OpenAI, and
Gemini through a Vercel proxy. Implemented in `brain/lm_direct.py` only. Keys are entered in *AI Models & Logs →
Direct fallbacks* (write-only, stored 0600) or via `DIRECT_<PROVIDER>_API_KEY`; Arvan/OpenAI/Gemini keys already in
`.env` are reused. A master switch and per-provider switches live in the same tab. Media routes (images, speech,
video) keep their own provider paths; direct fallback never applies to them.


## Priority and per-feature routes

Order everywhere: **Jarvis → Sarovi → ArvanCloud → OpenAI**; Gemini/Google models are asked of Google itself first. LM API (`lmapi.rafiei.co`) is tried first, then the direct fallbacks in the same order (*Direct fallbacks* tab, master switch on).

New AI stages have their own route card at the end of *AI Models & Logs → Routing*: Long Video (Transcript Enhancement, Topic Outline, Clip Finder, Clip Validator), Social Reference (Frame Review, Style Analysis) and Script Engine (Writer, Critic). New routes are seeded in priority order; **Apply priority to all routes** reorders existing chat/vision routes the same way (order only; nothing is added, enabled or removed). Sarovi text-model ids are not in the shared catalog: add them in the routing tab and press the button again.

# Provider routing policy

All hosted text, planning, translation, correction, vision and image-generation requests use the configured Arvan endpoint and its `Authorization: apikey` scheme. No external model fallback is enabled.

- Text: `ARVAN_AI_MODEL` (current installation: GPT-5.6-Sol).
- Vision: `ARVAN_VISION_MODEL` (Gemini-3-Flash-Preview, served by Arvan).
- Images: `ARVAN_IMAGE_MODEL` (Gemini-3.1-Flash-Image-Preview, served by Arvan), chat completions with image/text modalities and validated inline image responses.
- Speech: ElevenLabs only, with Localize's voice/model settings and the mandatory `ELEVENLABS_PROXY_URL` HTTPS relay. Missing relay configuration fails closed; no direct API bypass.
- Transcription: existing ElevenLabs Scribe or local Whisper; no retired hosted transcription fallback.
- Music: existing library and uploaded files. AI music generation is unavailable until a supported Arvan audio-generation contract is configured; the compatibility endpoint returns an actionable error.

Old saved provider names are normalized at execution time, while historical messages and existing rendered files are preserved. Restart the API and workers after deploying; already-running old processes retain their imported code.

Verified against the installation's live model list: text completion, image analysis, inline generated image and a short playable ElevenLabs voice clip through the relay. Unit tests additionally guard against retired provider names in runtime source and silent provider substitution.

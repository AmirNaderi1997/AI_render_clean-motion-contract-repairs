# Media routing and local STT fallback

`python -m scripts.enable_media_routes --apply` enables the existing media task
routes, preserves their exact selected IDs, sets modality-specific endpoint
types and minimum timeouts, and leaves paid retry/fallback disabled. It saves
a settings backup under `JOBS_DIR/ai_gateway/backups`. No inference is performed.
Untested models/contracts are not marked verified by enabling a route. Video,
music and image-edit contracts that lack a verified adapter remain blocked;
an enabled configuration is not proof of supported generation. The current
catalog contains no Scribe ID for Jarvis/Sarovi; those fallback slots are skipped
until a verified gateway STT model is registered. Own ElevenLabs through Vercel
remains first. No invented Scribe ID, substitution with AVEVOICE or `auto`.

Direct fallbacks now include a separate Local Whisper setting (enabled, model,
low-confidence text improvement), independent of direct text-provider keys.
Talking, Localize and generic transcription use the shared pipeline: own
ElevenLabs via the existing Vercel relay, Jarvis ElevenLabs via Gateway,
Sarovi ElevenLabs via Gateway, then optional local Whisper. One request per
remote provider, no automatic retry of the same provider. Jarvis/Sarovi require
registered verified Scribe IDs; absent models are skipped, not invented.
Whisper model assets can be preinstalled under `/root/.cache/editor-whisper/small`
on production (existing 100 GB cache bind mounts) or the local job sibling
`cache/whisper/small`. `WHISPER_LOCAL_MODELS_DIR` overrides this location.

AI correction only examines low-confidence words, reuses existing acoustic
similarity guards, auto-applies >=0.90 confidence one-word replacements and
preserves raw words/timestamps. Other suggestions stay reviewable in
`whisper_ai_review.json`. It cannot reconstruct missing speech from text alone.
An empty transcript remains an error rather than an invented transcript.

Talking 2 FFmpeg rendering explicitly uses one complex-filter worker, one
decoder thread per branch, two encoder threads and yuv420p branch formats.
This avoids host-wide automatic worker allocation inside CPU-limited VPS
containers. Encoding quality, color settings, captions and timing are unchanged.
Regression verification includes an actual 24-branch picture/audio render.

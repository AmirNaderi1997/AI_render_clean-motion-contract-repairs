# Source-edit delivery repair

Scope: the Talking 1 renderer used by Studio source edits. Owner: Codex. Baseline: `9afcf0a`; affected job: `21506adc1a34`.

The final composition inherited the millisecond-rounded Matroska/concat clock. Delivery now applies `fps=30` after joins and overlays, pads up to two tail frames for concat/EOF rounding, caps the planned frame count, and encodes CFR at 30 fps with a 30000 Hz MP4 video timescale. Audio timestamps and cuts are unchanged. The existing technical QC tolerance is unchanged.

The empty dark pill was the permanent hook background emitted for an empty hook. Empty or whitespace-only hooks now emit neither background nor text. Caption anchors and populated hook behavior are preserved.

Regression coverage: `tests/test_source_edit_delivery.py` checks empty-hook drawing events and renders actual cut/concat media with non-frame-aligned boundaries, checking exact frame rate, every frame timestamp, duration, audio stream length and a source-timed audio pulse. The encoding test reproduces the frame-rate failure on the deployed FFmpeg 7.1.5 baseline. On local FFmpeg 9 the baseline automatically chooses CFR; both empty-hook cases still reproduce locally.

Release procedure: run the full offline suite, push to fork, verify the VPS still has the expected clean baseline, tag its current runtime `pre-<new-sha>`, build only the app runtime with the existing Compose overlays, then recreate app/Hermes/worker/beat with `up -d --wait`. No schema or configuration changes. Rollback uses the retained runtime image. Re-render the existing transcript and plan via cached-only Talking rendering with provider calls blocked. Keep deployment logs, QC, probe, audio sync checks and the three original speech timestamps under `/root/stt-gemini-aligned/final/`. No acceptance examples or paid calls are authorized.

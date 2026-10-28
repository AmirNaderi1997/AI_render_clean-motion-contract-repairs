# Studio product motion: HyperFrames first, Remotion fallback

The failed export in job `5d095dbc2dd7` used the site's social-preview screenshot
as scene one, then enlarged square product photos to portrait with destructive
cropping. Six `uploaded_image_motion` clips were stitched and captioned through
MLT. This path did not invoke HyperFrames. Its QC report detected six issues,
including four framing errors, but reported `done` without applying any fix.

## Current path

Public page → structured/gallery images (social previews excluded when product
evidence exists) → content-hash deduplication → image-provider inspection →
numbered visual catalog → script with `source_asset_index` → approved storyboard
→ existing ElevenLabs narration/cache → speech alignment → fixed HyperFrames page →
technical export checks → required visual QC → publish a new version.

`app/jobs.py::_run_job` defaults to `REEL_ENGINE=hyperframes` and calls
`engine/remotion_renderer.py::prepare_reel_config`, then
`engine/hyperframes/product_reel.py::render`. A HyperFrames failure records
`renderer_failure` and renders a Remotion candidate. That engine switch holds
the candidate as `needs_review`; passing technical/visual checks cannot silently
publish it. An explicit non-HyperFrames `REEL_ENGINE` selects Remotion directly.

The existing Localize and Talking renderers retain their own engines. Product
shots are motion-designed from real photos. No claim is made that this adapter
generates live-action product footage. Scene B-roll is selected from the owned
catalog; unrelated stock is not substituted. Text-only/generated-media projects
continue through the existing provider route.

HyperFrames 0.8.161 is pinned in `engine/hyperframes/cli.py`; Remotion 4.0.536
packages are pinned together in `remotion/package-lock.json`. Maintained Python
templates generate HyperFrames HTML and a paused GSAP timeline. Maintained React
components render the fallback. Models supply validated data only; authored
HTML/CSS/JS/JSX is not a supported input. The chat motion graphic is disabled.

`engine/motion_contract.py` applies to both engines: 1–30 scenes, integer scene
frames from 1–900, total at most 2700 frames (90 seconds at 30 fps), at most
three supporting assets, owned media and approved-library music. The delivery
contract is 1080×1920 at 30 fps. HyperFrames copies local Ray font assets;
Remotion uses `RAY-EXTRABOLD.TTF`. HyperFrames captures one worker with a default
5400-second timeout. Remotion defaults to concurrency two and the same timeout
(overridable with `REMOTION_TIMEOUT_S`), H.264 CRF 18 and AAC.

## Speech-timed captions

For new Content Creator narration, `brain/tts.py` requests the relay's
`/v1/text-to-speech/{voice_id}/with-timestamps` endpoint. The checked-in relay
allow-list admits it. The response carries audio and character alignment;
`engine/narration_alignment.py` stores word starts/ends in
`<narration>.words.json` with the audio SHA-256. The audio-only gateway route
continues to use its configured provider policy.

Older/gateway audio without usable TTS timing uses
`brain/transcribe_elevenlabs.py::transcribe_elevenlabs`. Its result is cached in
`narration_alignment/<audio_sha256>/words.json` within the job. Identical audio,
including a renamed file or a second scene, reuses that cache. Script changes
are mapped again; the cache never replaces the script's display spelling.
Arabic/Persian letter variants, punctuation, digits and joiners are normalized
only for matching. Missing content, changed numbers, invalid/overlapping times,
out-of-scene times or ambiguous script-word boundaries reject alignment.

Both the HyperFrames reel and cinematic `DirectedReel` use the mapped starts
for four-word pages and the measured word ends for active colour. The cinematic
Remotion wipe lead is accounted for. The classic `DirectedReel` look and
`ProductReel` (`remotion/src/video.jsx`) show animated overlay titles without
narration word captions.

When alignment fails, `word_times` remains an explicit letter-weighted fallback
in HyperFrames; the cinematic Remotion caption fallback is also estimated.
The job records `caption_timing: "estimated"` in render state and technical QC,
along with per-scene evidence, and holds the candidate. The job prepares timing
once before selecting the engine, so fallback does not repeat a paid ASR attempt.
`caption_timing.json` retains the latest job's timing evidence.

Visual QC failure or a serious unresolved issue produces `needs_review` and
prevents publishing the new motion export. Proposed patches are never treated
as verified fixes. A failed vision-provider request does not pass visual QC.
An existing failed/unresolved candidate is `needs_review`; failure without any
candidate is `error`. Neither is added to published history.

See [motion-caption-evidence.md](motion-caption-evidence.md) for branch-specific
tests, fixture commands, comparison with local-only work and pending checks.
An offline fixture does not verify the deployed relay or provider pronunciation.

## Official references consulted

- https://github.com/remotion-dev/remotion
- https://www.remotion.dev/docs/
- https://www.remotion.dev/docs/ssr-node
- https://www.remotion.dev/docs/renderer/select-composition
- https://www.remotion.dev/docs/renderer/render-media
- https://www.remotion.dev/docs/sequence
- https://www.remotion.dev/docs/animating-properties
- https://www.remotion.dev/docs/fonts
- https://www.remotion.dev/docs/captions
- https://www.remotion.dev/docs/license

Remotion is source-available under its own license; company use may require a
paid license depending on the license terms. Installing it does not purchase
or activate a commercial license.

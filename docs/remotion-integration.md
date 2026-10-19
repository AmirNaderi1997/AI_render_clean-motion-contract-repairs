# Studio product motion: audit and render contract

The failed export in job `5d095dbc2dd7` used the site's social-preview screenshot
as scene one, then enlarged square product photos to portrait with destructive
cropping. Six `uploaded_image_motion` clips were stitched and captioned through
MLT. This path did not invoke HyperFrames. Its QC report detected six issues,
including four framing errors, but reported `done` without applying any fix.

## Current path

Public page → structured/gallery images (social previews excluded when product
evidence exists) → content-hash deduplication → image-provider inspection →
numbered visual catalog → script with `source_asset_index` → approved storyboard
→ existing ElevenLabs narration/cache → fixed Remotion React composition →
technical export checks → required visual QC → publish a new version.

The existing Localize and Talking renderers retain their own engines. Product
shots are motion-designed from real photos. No claim is made that this adapter
generates live-action product footage. Scene B-roll is selected from the owned
catalog; unrelated stock is not substituted. Text-only/generated-media projects
continue through the existing provider route.

Remotion 4.0.536 packages are pinned together in `remotion/package-lock.json`.
The server image installs Chromium and Node. At runtime only allow-listed scene
data enters a fixed React component; model-generated JS is never executed.
Assets must resolve within the current job. Fonts are loaded explicitly from
the existing Ray ExtraBlack file. Music uses the existing library, including a
disk scan when its persisted index is stale. Rendering progress comes from
Remotion's `onProgress`, concurrency defaults to two, and processing has a
30-minute limit. Exports use H.264 CRF 18 and AAC at 1080×1920/30fps.

Visual QC failure or a serious unresolved issue produces `needs_review` and
prevents publishing the new motion export. Proposed patches are never treated
as verified fixes. A failed vision-provider request does not pass visual QC.

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

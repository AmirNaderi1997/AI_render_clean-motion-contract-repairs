# Motion.so as a complementary composition tool

Existing path: Studio → approved storyboard → per-scene assets → owned media
checkpoint → narration/music → existing generic timeline/MLT or Remotion render.
Talking 2 has a native FFmpeg split-screen compositor with captions applied after
the upper/lower picture stack. Talking 1 is unchanged.

Motion is now an optional per-scene tool, not a replacement for these engines.
REST uses `https://api.motion.so/api/motion`, explicitly `engine=motion`, default
`effort=light`. Account discovery confirmed Motion light/medium/high and GVA
standard/extended; account defaults are never allowed to silently select GVA.

## Use

- Ask Studio explicitly for Motion.so; review the storyboard before approval.
- In Edit → Storyboard, choose Motion.so per scene, visual direction, effort,
  solid background and duration. Existing scenes keep their current tools.
- Edit → Motion.so creates/reuses a standalone owned scene, previews it, and
  inserts it as generic timeline B-roll where that engine exposes a plan.
- In Talking 2, select an existing sentence and assign the ready clip to its
  upper panel. The speaker stays below; source voice, Ray captions and timing
  stay local. Motion clips advance continuously across cut pieces. Other
  sentences retain the speaker. This explicit panel mode replaces HyperFrames
  for that Talking 2 render; it does not auto-generate replacement pictures.

The API response is a flattened MP4, not editable React/HTML layers. Alpha is
not documented. Do not claim transparent overlays. Exports are downloaded to
the owned job, normalized to scene duration/frame size/30fps, and stripped of
audio. Requested no-media/no-text instructions guide Motion but are not a
provider-enforced guarantee; preview before publishing. Local checks verify
duration, video stream and audio removal, not creative quality.

## Activity and safety

REST POST is one-shot. Durable request state is written before submission.
An uncertain POST is never retried. Existing remote IDs are polled, not recreated.
Expired download URLs are refreshed through the same status endpoint. Ready
files are cached by visual brief/reference hash. No automatic paid fallback.

MCP is used **only** for public assistant narration via `list_chat_messages`,
whose actual schema was read from tools/list. Cursor-based polling (5 seconds,
subject to API latency) retains the last message to observe streaming edits.
It is not a claimed WebSocket/token stream. Persisted messages enter the existing
Studio SSE activity UI as Motion Agent events; stable source IDs deduplicate
refresh/reconnection, including partially updated messages. Private reasoning,
user messages, code fences, bearer keys and upload credentials are not shown.
Message-read failures do not retry generation or prevent video delivery.

API calls require explicit user approval and Motion credits. Exact cost is not
available from the published REST contract. No paid generation was used during
implementation verification. No remote cancellation endpoint is documented;
UI does not claim to cancel a running remote job or its charges.

`MOTION_API_KEY_FILE` is server-only; `.motion_key` is excluded from Git and Docker
build contexts. `MOTION_ENABLED` gates submissions. Output downloads and uploads
accept only the documented HTTPS GCS host, no redirects or forwarded API token.
All Editor asset endpoints check job ownership. Timeline insertion uses the
existing validated, versioned save-plan path; Talking panel selections retain
their prior mappings in history. Other central media routes remain disabled.

Official references: https://docs.motion.so/llms-full.txt,
https://docs.motion.so/openapi.json, https://docs.motion.so/reference/sessions,
https://docs.motion.so/guides/mcp, https://docs.motion.so/guides/claude,
https://docs.motion.so/guides/attachments.

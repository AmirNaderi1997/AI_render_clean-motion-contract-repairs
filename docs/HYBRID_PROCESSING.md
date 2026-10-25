# EditorGPT: local processing, PWA and private companion

## AI project rendering bridge

Chat remains the AI editing entry point in every processing mode. The optional
quick-source exporter is deliberately nested and labelled as **not** the AI
project. Sending local assets requires explicit permission naming the destination
origin. LAN sends to a verified local backend, never a cross-origin cloud proxy;
AI providers can still receive the analysis inputs they require.

The full local EditorGPT backend runs the existing Talking, Localize and motion
engines. It does **not** need the restricted quick-trim companion. Project render
selection is persisted separately from AI execution mode. A `browser` target is
inherited by newly created projects, prevents native approval/resume, and holds
automatic motion rendering. Switching to native rendering requires the project
destination control and preserves the existing assets and approval workflow.

The browser AI adapter reuses the actual `remotion/src/video.jsx` ProductReel
composition, not a substitute montage. It consumes the existing authenticated
revision-bound manifest and prepared assets (max 90 seconds), checks WebCodecs
and codecs, reports progress and cancellation, and downloads the resulting MP4
locally. Saving that output back to the project is a separate approved transfer.
This adapter does not support arbitrary HyperFrames/FFmpeg/Talking/Localize
timelines. Those projects stay blocked for device export until an explicit native
destination is chosen. Never represent the quick-trim companion as their renderer.

Remotion web rendering sends licensing telemetry; its license eligibility and
commercial terms must be reviewed by the operator. No license eligibility is
implicitly declared by the application. Browser-render tests intercept external
requests and use only synthetic assets, not paid AI generation or user media.

## Architecture audit (baseline c472fd8)

This is additive, not a new editor. React 18 + TypeScript + Vite 5 builds the SPA;
React Router owns routes. `web/src/api.ts` uses same-origin `/api`, including the
authenticated event streams. Vite proxies those paths to FastAPI; production
Caddy serves the static build and proxies the existing API. Authentication is
JWT + refresh cookie; passwordless development is loopback-only. LAN clients
must sign in. Do not enable a LAN authentication bypass.

`app/studio_orchestrator.py` dispatches chat work into Talking, Localize,
long-video discovery, storyboard and motion-graphic flows. `studio_store` keeps
conversations/projects/versions/events in PostgreSQL or a development JSON store.
Celery handles background work with a local-thread fallback. Stop/busy markers
are shared on disk (`studio_flags`). Existing jobs, queues, models, providers,
AI routing, ownership checks and native render APIs are preserved.

Rendering is not one portable function: MLT/native FFmpeg (`engine/render.py`,
Talking, ASS overlays), HyperFrames/Chromium, Remotion and specialized motion
services have different contracts. `app/browser_render.py` already packages a
restricted ProductReel composition, not an arbitrary talking/editing timeline.
It is left intact. `engine/hyperframes/standalone.py` and all native engines are
left intact. The new companion executes a *restricted basic edit protocol*, not
user shell commands, generated HTML or arbitrary FFmpeg filters.

Previously Studio uploaded selections immediately; files were validated by
Pillow/ffprobe and persisted as owned attachments. The media library, historical
assets and existing exports stay server-backed. This increment changes Studio
ingestion only; specialist legacy upload pages retain their existing behavior.
There was no manifest or service worker. Safe-area variables, dynamic viewport
height and a VisualViewport listener already existed and are reused.

### Execution boundaries

| Operation | Execution |
|---|---|
| File registration, metadata, preview, draft | Browser, no AI required |
| Short basic trim/concat/cover-crop/resize/static text | Browser if actual APIs/codecs are supported |
| Same basic video edits, larger files | Paired FFmpeg companion |
| Talking templates, exact subtitles, advanced timeline/effects, HDR guarantees, motion engines | Existing native backend; not falsely marked device-compatible |
| AI analysis/generation | Existing configured providers, called by backend. Local backend does not make a cloud model offline |

## Central settings and data destination

Settings → **Processing & this device**:

- **Online** (default): the previous workflow, including immediate selection
  upload to this installation's backend. The production installation uses its
  existing cloud backend; a development installation still uses its local backend.
- **This device**: selections are local, best-effort persisted; sending them to
  an AI/server operation asks before upload. Local export is available inside
  the composer after selecting video. Other legacy specialist pages are not yet
  converted to local-first ingestion.
- **LAN**: uses the *full local EditorGPT installation* at its private address
  / `.local` hostname. HTTP permits basic access; HTTPS is required for PWA and
  secure browser features. It must report `local_installation: true` from
  `/api/health`, or have a local Vite runtime confirming a loopback API target
  and a successful backend health check. Empty local URL uses the current origin.
  All relative API, AI, project and SSE calls then go to that local installation.
  This is deliberate navigation, not an invisible cross-origin proxy. Sign in
  there normally; cloud projects/history are not copied or uploaded automatically.
  Switching to Online restores immediate uploads to the current installation;
  it does not silently change which backend receives the files.

### Optional local HTTPS on this Mac

Run `python scripts/prepare_lan_tls.py --ip YOUR_PRIVATE_IP --name mac-2.local`.
Keys stay in ignored `.local-lan/`; never share its private key files. Set
`EDITOR_DEV_CERT` to `server.pem`, `EDITOR_DEV_KEY` to `server-key.pem`, and
`EDITOR_LAN_CA` to `ca.pem` using absolute paths when starting Vite. A separate
HTTPS preview may run on port 5190 alongside HTTP development on 5187.
`/__local/ca.cer` serves only the public root certificate. Each iOS/iPadOS device
must install that profile and explicitly trust this root under Settings → General
→ About → Certificate Trust Settings. No trust-store changes are automatic.
Keep the Mac awake and both devices on the same trusted, non-isolated Wi-Fi.

Configure that local backend with its own server-side API keys/routes in
`/settings/ai`. Do not place keys in frontend settings. Internet AI providers
still receive whatever text/frames/audio their requests require. The original
video need not be uploaded to the *EditorGPT cloud server*. Fully offline AI
requires a separately supported local model integration and is not implemented.

The companion pairing and the default local export engine are also in Settings.
Export shows the chosen engine / recommendation, destination and size before
starting; selecting Auto never consents to transfer. This first export UI works
on selected original videos, not the entire AI-authored timeline. Unsupported
operations are rejected; they are never silently dropped or uploaded.

## Run on this Mac and LAN

From repository root, configure the existing backend environment and dependencies:

```sh
EDITOR_LOCAL_INSTALLATION=1 .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In `web/`:

```sh
npm run dev
# http://localhost:5187, loopback only (default)

npm run dev:lan
# explicitly opt in to 0.0.0.0:5187 on a trusted private Wi-Fi network
```

`API_TARGET` defaults to `http://127.0.0.1:8000`. Set it to another **loopback**
backend port if needed; do not point it at the cloud when claiming LAN execution.
The browser does not call a hard-coded localhost backend: Vite proxies `/api`.
LAN proxy requests have a non-loopback backend Host, preventing them from
inheriting the local developer identity. Vite rejects non-private peer addresses.
Its dev-only `/__dev/network` lists private IPv4 links, shown in Settings.
Backend need not listen on LAN or add wildcard CORS. Existing authenticated SSE
uses the same proxy; HMR is Vite's existing transport.

For secure-context features on mobile, provision a certificate for your Mac's
private IP or `.local` name that the phone actually trusts. For example a local
development CA may be used; trust its **public CA certificate** on each device,
never copy its private key. Then start the frontend:

```sh
EDITOR_DEV_CERT=/absolute/path/editor.pem EDITOR_DEV_KEY=/absolute/path/editor-key.pem \
EDITOR_LAN_HOST=editor-mac.local API_TARGET=http://127.0.0.1:8000 npm run dev:lan
```

Open `https://editor-mac.local:5187` (or the certificate's private IP).
Plain `http://192.168.x.x:5187` supports basic access but not full PWA, secure
storage/crypto, notifications, or every media API. Do not bypass TLS errors.
macOS Settings → Network → Firewall: allow the selected Node/Python executables
only for the trusted network. No router port forwarding, tunnels or public
reverse proxy for development. Guest Wi-Fi/client isolation may block LAN peers.
No QR library or automatic mDNS discovery is added; address entry is explicit.

## PWA

`npm run build` emits a versioned `/sw.js`, public manifest and app/touch icons.
Serve `web/dist` over HTTPS with SPA fallback. Do not apply immutable long-lived
caching to `sw.js` or `index.html`; hash-named `/assets` may be immutable.
The service worker precaches a public shell and hashed static modules only.
It never caches `/api`, authenticated requests, query URLs, user uploads,
outputs or arbitrary network responses. Offline shell is not offline login or
offline AI. Existing authentication is still required for protected workflows.

- iOS/iPadOS: Safari → Share → Add to Home Screen.
- Android/desktop: browser install action or Settings → Application → Install EditorGPT.
  If the browser does not offer a native prompt, that row shows installation instructions instead. There is no floating Install overlay in chat.
- New versions wait; Settings → Application offers Update app before reloading. Do not update during
  a device render. Background/locked-screen device rendering is not reliable.
- Existing safe-area / `--app-h` / VisualViewport behavior is preserved. New
  controls have 44px targets and 16px input text; real iOS keyboard testing is pending.
- Notification permission is requested only in Settings. Completed local exports
  can show a permitted notification/haptic. No Web Push subscription or push
  delivery backend is included; cloud-background push and completion sound are
  not claimed implemented.

## Local storage

Media is owner/project-scoped in IndexedDB. OPFS is preferred for media bytes,
using `File.stream().pipeTo()` rather than whole-file JS buffers. On browsers
without writable OPFS, IndexedDB Blob persistence is limited to 128 MB; larger
files remain session-only with a visible warning. The input original is never
changed. Metadata uses browser media decoding with a timeout. Unsupported
preview codecs do not destroy the original.

Quota is checked with safety headroom; persistence is opt-in. Settings shows
usage and has account-scoped local media cleanup. Draft text and pending files
are recovered after reload where available; missing/evicted files ask for the
original again. Do not promise permanent iOS storage or automatic cleanup of all
possible OPFS orphans after browser/process crashes. Keep independent originals.

## Browser export subset

The real engine uses canvas capture + MediaRecorder + Web Audio. It probes actual
container/codec support; current preference is MP4/H.264/AAC, then WebM/VP8/Opus.
Presence of WebCodecs/OffscreenCanvas is reported internally, not falsely treated
as a complete encoder/demuxer. FFmpeg.wasm is not downloaded; its large-file copy
and mobile-memory costs are avoided in this increment.

- Up to 8 browser-decodable videos, 512 MB input total, 120 seconds combined,
  output at most 720p-equivalent area (1280×720 or 720×1280).
- Same trim interval on each clip; sequential concat, cover-crop/resize, one
  static text strip. No automatic AI, B-roll, new paid media or upload.
- Approximate real-time cuts, not guaranteed frame-accurate NLE export. No
  transitions, multi-track audio mixing, timed subtitle styles, HDR preservation
  or complex effect parity yet. Output is bounded to 96 MB and kept as a Blob.
- Cancel, decode/encode errors, stalls and background interruption are reported.
  A failed device render does not automatically switch engines. Resume requires
  an explicit restart from local inputs, not continuation of a half-encoded file.

## Restricted LAN companion

The optional companion is **not** mounted into the main cloud API. Start it with:

```sh
.venv/bin/python scripts/lan_worker.py
# loopback HTTP only, for same-computer testing; port 5188

.venv/bin/python scripts/lan_worker.py --host 0.0.0.0 --port 5188 \
  --cert /absolute/path/editor.pem --key /absolute/path/editor-key.pem \
  --allowed-host editor-mac.local --allowed-host 192.168.1.10 \
  --origin https://editor-mac.local:5187 --origin https://editor.rafiei.co
```

Pair in Settings with the printed random code (5-minute expiry, bounded failed
attempts). A 24-hour bearer session authenticates health, asset transfer, job,
status, cancellation, output and cleanup. CORS origins and Hosts are exact,
not wildcard. Production PWA → HTTPS companion requires a genuinely trusted
certificate and browser local-network permission; support is not universal.
If blocked, open the same HTTPS local installation directly; no HTTP mixed-content
workaround or TLS verification bypass is attempted.

Transfers hash one 4 MB chunk at a time in a Web Worker. The manifest ID is
SHA-256(size + ordered chunk hashes), **not** the standard whole-file SHA-256.
Worker verifies every chunk, reuses already-owned assets and reports missing
chunks for retry. Limits: 2 GB per asset, 8 clips, 10-minute output, 1080p-equivalent
area, 10 GB storage budget plus 512 MB free-space reserve, single render executor.
Requested media is ffprobed; external protocols/playlists are rejected. Paths,
filter strings and executable names cannot be supplied by clients.

FFmpeg uses bounded threads, libx264/AAC, normalized audio tracks, restricted
demuxers, progress parsing and termination on cancel. Jobs use idempotency IDs;
a duplicate ID with different instructions is rejected. Normalized intermediates
are removed after completion. Originals/results stay until explicit per-pairing
cleanup, and cannot be read by another pairing.

A computer job survives mobile navigation/backgrounding while the worker runs;
sessionStorage retains the pairing/job so **Reconnect to last job** can retrieve
it without regeneration. Explicit Cancel sends DELETE. Worker restart/24-hour
expiry currently invalidates the in-memory pairing/job registry. Disk files
remain under `~/.editorgpt-worker` (or `--root`); automatic durable recovery across
worker restart and automatic TTL garbage collection are **not implemented**.
The companion does not yet submit full Talking/MLT/HyperFrames timelines.

## Verification and scope

Changed/new source groups:

- `web/vite.config.ts`, `web/pwa-build.ts`, `web/package.json`, `web/index.html`:
  opt-in LAN development and production shell generation.
- `web/public/manifest.webmanifest`, `web/public/icons/*`,
  `scripts/make_app_icons.py`: install identity/icons.
- `web/src/local/{preferences,storage,render,lan,hash.worker}.ts`:
  settings, persistence, feature detection, device engine and companion client.
- `web/src/local/{AppFeatures,LocalExport}.tsx`, `web/src/{main,Settings,Studio}.tsx`,
  `web/src/studio/Composer.tsx`, `web/src/styles/studio.css`: additive UI wiring.
- `app/main.py`: additive local-installation health marker.
- `app/lan_worker.py`, `scripts/lan_worker.py`: opt-in native companion.
- `tests/test_lan_worker.py`, `web/tests/local-render.test.mjs`,
  `web/tests/local-media.browser.mjs`, `web/tests/pwa.browser.mjs`: checks.
- `docs/HYBRID_PROCESSING.md`: architecture, instructions and phase limitations.

Automated checks use synthetic media, not private files or paid model calls:

- Backend: pairing/origin/host guards, invalid chunks, resumable manifests,
  cross-pair isolation, deduplication, idempotence, native FFmpeg output + ffprobe,
  protected output and cleanup. Existing Studio/Gateway/media regression subset.
- Frontend: unsupported-operation routing, existing model/timeline tests,
  TypeScript + production build.
- `node web/tests/local-media.browser.mjs` (run from `web/` with Vite on 5187):
  imports without POSTs in Device mode, real H.264 + audio export, verifies
  dimensions/streams using ffprobe, reload recovers local draft; Online immediate
  upload is verified with intercepted API responses.
- `node tests/pwa.browser.mjs` from `web/`, with `vite preview` on 5189:
  real service worker, manifest, offline shell and no sensitive cache entries.

No physical iPhone/iPad/Android, Windows hardware encoder, keyboard, certificate
installation or production Home Screen installation has been tested. Chrome on
macOS is not an iOS test. Full production AI/cloud generation is not executed.

### Phase status and next work

1. Audit/LAN: implemented dev access, proxy safeguards and instructions; real
   phone connectivity still needs device acceptance.
2. PWA: shell, install assets, safe update and opt-in foreground notifications;
   real-device installation/keyboard and server push remain.
3. Local-first: Studio implemented behind Settings mode; specialized upload
   screens and more robust cross-tab/crash storage lifecycle remain.
4. Device: working bounded basic subset; full timeline mapping, timed captions,
   transitions, audio mixing and hardware-specific qualification remain.
5. LAN: working restricted FFmpeg companion; durable registry/restart recovery,
   revocation UI, TTL cleanup and richer existing-engine job adapters remain.
6. Selection: Settings, explicit consent and shared states for this subset;
   integration into every legacy export/AI project still remains.
7. Verification: local automated checks completed; this is not a claim that all
   requested cross-device production acceptance scenarios are complete.

No deployment, server restart, Git commit or change to production AI routes is
performed by this implementation. Review and device acceptance should precede
production release.

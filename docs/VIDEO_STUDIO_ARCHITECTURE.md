# Video Studio architecture

`/studio` is a conversation-first layer over the existing production engines. It does not let the language model call arbitrary URLs, endpoints, code, or shell commands. The orchestrator resolves a request into one of the typed tools in `app/studio_tools.py` and the adapter invokes the existing engine.

## Engine map

| Studio intent | Existing implementation | External reference | Progress source | Output |
|---|---|---|---|---|
| Persian localization / dubbing | `app/localize.py` | Localize id | persisted Localize state | Localize export |
| Talking-head social edit | `app/talking_reel.py` + `engine/talking_reel` | Job id | Talking state | Talking export |
| URL, image, or text motion reel | `brain/content_creator.py` | Job id | generation checkpoint + render state | generic job export |

Talking styles always come from `engine.talking_reel.style_list()`. A missing style is a required conversational question before analysis or render. Motion requests normalize URL facts, uploaded images, or a text brief into the same storyboard model. Uploaded and downloaded images are copied into the owned job before generation.

## Persistence and execution

- PostgreSQL tables separate conversations, messages, attachments, projects, project versions, actions, and ordered events.
- Local development without `DATABASE_URL` uses an atomic JSON store under the local jobs directory; production uses PostgreSQL.
- Long work is dispatched through the existing Celery application when configured, with a local worker thread fallback for development.
- Project versions are appended when an edit changes project state. Old engine outputs remain addressable through their original project records.
- SSE events are persisted with a per-conversation sequence. `Last-Event-ID` and `after` resume without replaying acknowledged events.
- Percentages are copied only from engine state. If an engine exposes stages but no numeric progress, Studio reports the stage without inventing a percent.

## Public API

The authenticated API is mounted at `/studio`: conversation CRUD, uploads, messages, resumable events, project/storyboard reads and edits, confirmation/cancellation actions, protected assets and outputs, tools, and capabilities. Server paths are removed from project and event responses.

## Security boundaries

- Attachments are scoped by user and conversation and validated by Pillow or ffprobe before use.
- Filenames are reduced to their basename; engine assets and outputs are served only after ownership checks.
- URL inspection accepts public HTTP(S) resources only, resolves DNS and validates every redirect, rejects credentials and non-global IPs, caps response sizes, and validates downloaded images.
- Visible page content, structured Product data, galleries, lazy image attributes, and `srcset` are inspected. Page content is untrusted evidence, never an instruction.
- Tool arguments use Pydantic `extra="forbid"`; only the allow-listed registry can execute an engine adapter.
- Expensive motion execution is represented by an idempotent pending action and begins only after confirmation.
- API keys, attachment paths, and server paths are not placed in the public event stream.

## Honest capability limits

- Localize preserves the source aspect ratio.
- Talking and Content Creator currently render 9:16. The Studio does not advertise 16:9 until the underlying render path supports it end to end.
- Localize and Talking expose real cancellation. The current Content Creator generation/render path does not expose a safe cancel token, so its cancel control is disabled rather than simulated.
- Status voice is optional and non-blocking. It uses the configured existing TTS provider and never delays the video pipeline.

## Acceptance verification

Automated tests cover parsing visible/structured product data, SSRF rejection, typed tools, intent/style routing, persistence/versioning/ownership, and public payload path scrubbing. The release smoke test creates a real 20-second 1080x1920 H.264/AAC motion output from an uploaded image with five generated narration clips, then checks the final streams with ffprobe. Localize and Talking adapters reuse the same tested pipelines already exposed by their existing UIs.

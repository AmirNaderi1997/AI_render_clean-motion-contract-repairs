# EditorGPT UI/UX audit and migration map

Date: 2026-10-19

## Product architecture

The product already has the correct conversational core. `Studio.tsx` talks to the
persisted Studio conversation API, uploads media, consumes the SSE event stream,
confirms actions, displays real projects and outputs, edits storyboards, and can
cancel supported work. The redesign therefore treats Studio as the product shell
instead of adding another orchestration layer.

The frontend is React 18 + TypeScript + Vite + React Router. Authentication uses
the existing token/refresh-cookie helpers and local-development bypass. Long-running
video work remains in FastAPI/Celery. No render or persistence contract needs to be
replaced for this migration.

## Route and feature inventory

| Current surface | Real capability | Decision | New location |
|---|---|---|---|
| `/studio` | Conversations, messages, uploads, SSE events, approvals, storyboard, preview/download | **KEEP + PROMOTE** | `/`, `/studio`, `/studio/:conversationId` |
| `/jobs`, `/jobs/:id`, `/jobs/:id/render` | Generic jobs, plan review, timeline, QC, render, versions, audio tools | **MERGE + KEEP LEGACY** | Unified `/projects`; detailed legacy links remain valid |
| `/talking`, Talking Reel editor | Talking-head analysis/render, media, logo, captions, CTA, zoom/color controls | **RELOCATE** | Talking Head template; detailed editor remains an advanced legacy route |
| `/localize` | Translation/dubbing/caption analysis, voice, render, pause/resume/cancel | **RELOCATE** | Video Localization template; existing project links remain valid |
| `/content` | Prompt/image/URL content storyboard and motion render | **MERGE** | Studio creation workflow and Product Commercial template |
| `/new` | Manual video upload and plan generation | **HIDE UNDER ADVANCED** | Advanced tools and legacy bookmarks |
| `/my-effects` | Effect preferences and feedback | **HIDE UNDER ADVANCED** | Settings → Advanced tools |
| `/style-library`, `/fonts` | Style profiles, evidence and font library | **RELOCATE** | Templates/Settings; legacy editor remains reachable |
| `/style-learner` | Reference analysis and learned style profile | **HIDE UNDER ADVANCED** | Settings → Advanced tools |
| `/library` | Music/B-roll/SFX/font/brand asset management | **HIDE UNDER ADVANCED** | Settings → Advanced tools |
| `/hermes/*` | Separate social account, schedule, analytics and advisor product | **REMOVE FROM MAIN NAV** | Settings → Integrations; all routes and data preserved |
| Auth/public routes | Landing, sign in/up, reset | **KEEP** | Unchanged |

## State and API inventory

- Studio: persisted conversations, messages, attachments, projects, actions,
  versions and events. SSE reconnects with an event cursor/`Last-Event-ID`.
- Generic jobs: uploaded source, plan, generate state, render state, QC, music,
  versions and export URLs.
- Talking Reel: generic job ID plus a talking state and output endpoint.
- Localize: independent project ID, source/output, analysis/render state, pause,
  resume and cancel.
- Content motion: generic job plus storyboard/generation status and plan/render.
- Authentication and authorization remain enforced by existing middleware and
  request-scoped job/project access.

## Status model

The backend has intentionally different state machines. The unified Projects view
uses a frontend adapter rather than changing them:

- idle/new/awaiting input → Draft
- queued/analyzing/transcribing/generating/processing → Preparing or Editing
- rendering → Rendering
- done/ready → Ready
- paused/awaiting confirmation → Needs attention
- error/failed → Failed

No synthetic progress is introduced. A percentage is displayed only when supplied
by the source API.

## Duplication and usability problems

- The permanent sidebar exposes eleven products and internal concepts.
- Jobs, Talking Reels, Localize and Studio each provide independent history lists.
- Studio mixes conversation navigation, chat, event logs and workspace without a
  stable mobile information architecture.
- Raw engine/status strings are shown directly to beginners.
- The 2,000-line global stylesheet is desktop-first and contains overlapping page
  rules; mobile mostly hides columns instead of creating a mobile workflow.
- Emoji are used as navigation icons and visual hierarchy is inconsistent.
- Home currently redirects to a technical upload form instead of the AI assistant.

## Migration constraints

1. Preserve all API contracts, backend capabilities, IDs, data and old URLs.
2. Make Studio the authenticated home and add path-based conversation URLs.
3. Add a four-item application shell: New Edit, Projects, Templates, Settings.
4. Build unified project cards using adapters over existing sources; do not create
   duplicate backend records.
5. Keep detailed legacy editors available from contextual advanced links.
6. Use mobile-first layout, safe-area insets, touch targets, sticky composer and
   Chat/Preview/Edit views.
7. Keep real event history, but translate common stages and collapse technical
   details by default.

## Acceptance verification

The migration must pass TypeScript/Vite build, current frontend-relevant tests,
mobile overflow checks, Studio upload/message/event/output flows, legacy deep links,
and production health checks. External AI/render operations are reported separately
when a provider cannot be exercised during UI verification.

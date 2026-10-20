# Frontend reconstruction — audit, architecture, results

Scope: `web/` only. No Python, API contract, schema, auth-backend or deployment file was touched
(`git status` shows changes under `web/` and `docs/` only).

## Audit: where the legacy look came from

`web/src/styles.css` (2,391 lines) was a stack of at least four redesign attempts. Root causes:

| Problem seen in the product | Source |
|---|---|
| Purple buttons everywhere | global `button { background:#4f46e5 }` + `--accent:#6366f1` |
| Content stuck in half the viewport | global `main { margin-left:var(--nav-width); max-width:1200px }` + fixed `.eg-*` offsets |
| Sidebar labels overlapping headings when collapsed | collapsed sidebar was `position:fixed` and only its width changed; page offset was a separate hard-coded margin |
| Chat/Preview/Edit tabs over messages | `.eg-view-tabs` absolutely positioned in the chat column on desktop |
| 263 dead rules | `.studio-*`, `.app-nav`, `.eg-history*`, `.eg-home*` … no component used them |
| Competing systems | `--eg-*`, `--hm-*` (Hermes, 25 KB with `!important`), legacy `--accent*` |
| `h1::after` purple bar, gradient cards | legacy typography/cards |

### Stylesheet → route dependency map (after)

| Stylesheet | Applies to |
|---|---|
| `styles/tokens.css`, `base.css`, `components.css` | every route (tokens, reset, buttons/inputs/badges/sheets/toasts) |
| `styles/shell.css` | authenticated shell: sidebar, drawer, topbar, bottom nav, page frame |
| `styles/studio.css` | `/studio`, `/studio/:id` |
| `styles/auth.css` | `/login`, `/signup`, `/forgot-password`, `/reset-password`, mobile auth sheet |
| `styles/pages.css` | `/projects`, `/templates`, `/settings`, `/welcome` |
| `styles/legacy.css` (scoped to `.eg-legacy`) | `/jobs/:id/render`, `/new`, `/content`, `/localize`, `/talking`, `/my-effects`, `/library`, `/style-library`, `/style-learner`, `/hermes/*`, `/settings/ai` |
| `pages/hermes/hermes.css`, `ai-models.css` | Hermes / AI-models only (re-tokenised, no `!important`) |

`legacy.css` cannot leak into rebuilt screens: every selector is prefixed with `.eg-legacy`, and the
bare-element defaults use `:where()` so component classes win without specificity wars.
`!important` remains only in the reduced-motion override (`base.css`, documented there).

## Architecture

* `AppShell` = CSS grid `[sidebar | content-col]`; `content-col` = `[topbar | main | bottom-nav]` with
  pinned rows. No offsets depend on sidebar width.
* Sidebar: expanded / icon rail (desktop, persisted), drawer with scrim, Esc, focus trap and `inert`
  background (≤820px). Collapse control is always visible.
* Studio layouts: desktop ≥1100 two panels (conversation | Preview·Edit tabs, collapsible);
  tablet 701–1099 slide-over workspace; mobile ≤700 one view + Chat/Preview/Edit bottom tabs.
  A single `Workspace` instance is mounted so video/storyboard state survives layout changes.
* `studio/model.ts` is a pure, unit-tested view-model: messages + SSE events → timeline.
* Auth: one `AuthFrame`/forms for all auth routes; on phones, in-app “Log in” opens a bottom sheet.

## Processing, activity and rendering — what is real

Everything is derived from events the backend actually emits (`message.started`,
`agent.thinking_summary`, `tool.started/progress/completed/failed`, `storyboard.ready`,
`question.required`) and `project.state.last_observed`.

* User message and a processing state appear before the send request returns.
* Stop button only when a project is running (`cancelStudioProject` exists); otherwise a
  non-cancelable spinner. No stop for the pre-project “thinking” phase (no backend support).
* Repeated progress folds into one step; history kept in `step.events`.
  A step shows ✓ once later work starts or the backend says completed (inferred, documented in `model.ts`).
* Expandable details only when there is something to show (backend note, timing, tool, error).
* Rendering is one inline card per project: stage, %, elapsed time → becomes the playable video with
  Download / Open in Preview / Edit again / version. The blurred backdrop is the user’s own uploaded
  source video; with no source it is a neutral skeleton. No poster or URL is invented.
* Labels like “Writing the storyboard” are UI-generated from tool/stage ids; the backend’s own text
  (Persian) is shown in the expanded details.

## Verification

* `npm run build` (tsc + vite) passes. `npm test` → 13 unit tests pass (model + existing ai-models).
* `npm run test:visual` (needs `npm run dev`, Google Chrome): 83 screenshots at 320–1920px,
  asserts no horizontal overflow and no console errors; `tests/visual/send-flow.mjs` asserts the
  immediate-processing behaviour and that every control has an accessible name.
* API responses in the visual tests are Playwright route fixtures (`tests/visual/fixtures.mjs`);
  the app contains no mock data. They are not a substitute for a run against the real backend.

## Known limitations / backend-dependent

* Not verified against the live backend or with real long renders; real event timing may differ.
* Historical attachments only expose ids, so previews are lazy (“Tap to preview”) instead of thumbnails.
  Thumbnails/poster URLs for conversations would need a backend field.
* No cancel for the assistant’s pre-project thinking phase; needs a backend endpoint.
* “Retry in chat” only pre-fills the composer; there is no dedicated retry API for failed renders.
* No real template preview assets exist; template tiles show format/category, not fake previews.
* The visual fixture for `/my-effects` does not match the real payload shape, so that page was not
  rendered with data in the screenshot run (it loaded without layout overflow).
* Legacy editors were re-skinned and re-scoped, not re-architected; they are still dense forms.
* Fonts load from Google Fonts (as before); offline they fall back to system fonts.

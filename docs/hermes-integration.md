# Hermes integration: architecture and implementation status

## Audited architecture

The existing `hermes/` application is EditorGPT's Instagram FastAPI service,
not NousResearch Hermes Agent. Its account ownership, encrypted settings,
scheduled publishing claims and authentication remain authoritative.

| Component | Existing responsibility | Integration boundary |
| --- | --- | --- |
| `hermes/main.py`, `routers/`, `security.py` | Instagram API, per-user authorization | Connected apps and bounded agent operations |
| `hermes/models.py`, `database.py` | Shared SQLAlchemy users; local JSON fallback | Encrypted provider settings and owned connection references |
| `app/agents/medium/` | LangGraph checkpoints, approval interrupts, tool ledger | Typed, bounded Hermes tools; no second render job lifecycle |
| `app/studio_tools.py`, `studio_activity.py` | Shared validated tools and public activity | Reuse for progress and permission enforcement |
| `creative/director.py` | Concepts, scripts, visual direction | Structured approved scripts, not automatic rendering |
| `brain/lm_gateway.py` | Provider configuration and accounting | Retained; no separate model defaults |
| Native FFmpeg, HyperFrames, Remotion | Media production | Unchanged |
| Official Hermes Agent | Native skills, conversational research | Separate managed runtime, not replacement of `hermes/` |

The independent local installation is official Hermes v0.22.5, revision
`bf0203a794a07aac3ff764972ab9087baa4e4f4e`. It has an isolated home and no model
credentials configured. Do not use its unrestricted terminal or raw MCP actions
as an authenticated web-user tool. EditorGPT must remain the permission boundary.

## Pinned Instagram skills

`scripts/install_instagram_skills.py` installs all 13 definitions and supporting
resources through Hermes' **native** quarantine, security scan, install ledger
and discovery. It does not create another skill registry or edit upstream files.
Source: Jake Schincariol's MIT-licensed `instagram-agent-skill`, pinned at
`d03c56bb598be770c60b201f94237e5d1a4268a6`. Every installed skill retains the license.
The voice template is a reference, not a shared user profile.

Run with the official Hermes managed Python, passing explicit source, runtime
and isolated home directories. The source checkout must match the pinned commit.
Existing installations are not overwritten. Upgrades require source review and
an explicit pin update. Removal uses native `hermes skills uninstall <name>`.

Important upstream limitations: its instructions refer to Claude home paths;
web integration must substitute authenticated project references, never a shared
`~/.claude/instagram` directory. Its English humanizer deletes Persian ZWNJ and
its English timing regex misses Persian words. Do not use those scripts directly
for Persian content. Heuristic scores are editing aids, not virality predictions
or scientific AI-authorship determinations.

## Connected-apps foundation

`hermes/services/composio_sessions.py` uses the official Sessions API from
Composio 0.30.0. `hermes/routers/connected_apps.py` uses existing JWT identity;
client-supplied identities/session IDs are rejected. References use encrypted
`HermesSetting` values, so no additional database migration is needed for this
foundation (the existing Hermes settings migration must already be applied).
Unknown applications, disabled integration and changed session policies fail
closed. Sandbox, arbitrary proxy execution and connection-management agent tools
are disabled. The session currently allows read-only tagged tools only.

Settings includes a small Connected Apps section, using the existing design
tokens. Enable/disable, explicit OAuth-link creation and connection checks are
implemented. A redirect is **not** considered a successful connection; status
comes from Composio. Disabling is not provider-side revocation.

No SDK execution endpoint, raw MCP URL or general proxy is exposed. External
mutations remain unavailable pending integration with the Studio approval ledger.

### Setup (not automatically deployed)

1. Install `requirements-composio.txt` in the **EditorGPT backend environment**,
   not in the official Hermes managed environment. Resolve alongside the existing
   application lock; do not update the running environment blindly.
2. Configure `COMPOSIO_API_KEY` via server secret management, never frontend env.
3. Set `COMPOSIO_INSTANCE_ID` to a persistent installation-specific random ID.
   Keep it stable across restarts; separate development and production IDs.
4. Set `COMPOSIO_CALLBACK_URL` to the installation's HTTPS `/hermes/settings` URL.
5. Set `COMPOSIO_TOOLKITS=instagram` (default). Only administrator-configured
   applications are allowed. Empty means none, not the whole catalog.
6. Keep a persistent `HERMES_ENCRYPTION_KEY` and existing database configuration.
7. Deploy/restart the Hermes service and frontend together after review. Open
   Settings, enable, choose Connect, complete hosted OAuth, then check connections.

Current tests use mocks only. Real OAuth, account revocation, multiple-account
selection and provider permissions require authorized integration tests before
production sign-off. No new background service or renderer is introduced.

### Rollback

Disable Composio in Settings, restore the previous frontend/backend release and
remove the optional dependency on the next environment rebuild. Existing Instagram
credentials/accounts are unchanged. Encrypted Composio settings may remain inert;
rolling back code does not revoke OAuth consent. Revoke consent at the provider
or Composio dashboard if required. Do not rotate encryption keys as a rollback.

## Pending acceptance gates

### Shared Studio/LangGraph content checks (implemented)

`instagram_content_check` is now registered in `app/studio_tools.py` and exposed
through the existing Medium tool catalog and strict EditingPlan schema. It uses
the same activity events, checkpoints, per-user run ownership and operation
ledger as existing editing tools. It is read-only, bounded and idempotent; no
approval is needed to inspect supplied text. A completed operation is reused
after recovery rather than executed again. No provider/model/agent-mode defaults
change. The planner is told to treat warnings as suggestions and never invent
metrics to improve a score.

Seven integration tests cover actual Persian checks, schema validation, activity
events, persisted results, replay protection and run ownership. Together with
the pre-existing Studio agent suite and content checks: 61 tests passed.

Dynamic discovery/execution through Hermes, backend-approved mutations, provider
revocation, per-user skill controls, scoped brand voice, structured Creative
Director handoff and Composio execution through LangGraph are not yet delivered. Installation alone
does not activate those paths. Policy changes currently need an administrator to
review/reset the affected saved session; there is no automatic widening.
No live account or paid model calls are required for installation tests.

Verified locally: all 13 skills passed native security scans and appear enabled
in `hermes skills list --source hub`; a second installation was a no-op for all
13. Three offline installer contract tests passed. No production changes were made.

`hermes/services/instagram_quality.py` now provides bounded execution of all six
original English helpers with fixed commands, stdin-only text, an eight-second
timeout, CPU/file-output limits and a credential-free environment. Persian hook,
caption, conservative normalization and beat-sheet adapters preserve ZWNJ/ZWJ
and support Persian/Arabic/English digits. Unsupported Persian scoring operations
fail explicitly; no synthetic virality score is substituted. Speaking duration
is an estimate, not forced alignment. Combined offline tests: 22 passed.
The reviewed upstream pack is vendored unchanged under `vendor/instagram-agent-skill`.
These helpers are not yet exposed as authenticated Studio/Hermes tools.

Composio implementation must use a stable server-derived user identity and reuse
persisted session IDs. Explicit toolkit allowlists and disabled remote sandbox
tools are required. Discovery is not authorization; every mutation must pass the
existing backend approval contract. API keys stay in server secret management.

Validation: 30 Python tests (including real Composio SDK with mocked HTTP), one
React/jsdom settings test and full frontend TypeScript checking passed. The SDK
contract test confirmed its public `sandbox` option maps to the API `workbench`
field with execution disabled. The SDK was installed only in a temporary test
directory; running local and production application environments were unchanged.
No hardware-specific mobile/PWA testing or live OAuth success is claimed.

Reviewed references: [Sessions](https://docs.composio.dev/docs/configuring-sessions),
[authentication](https://docs.composio.dev/docs/authentication/manually-authenticating),
official `composio==0.30.0` wheel source and the pinned Hermes source above.

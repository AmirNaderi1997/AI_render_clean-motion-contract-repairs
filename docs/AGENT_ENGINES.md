# EditorGPT Lite & Medium

## Architecture assessment

This is an additive Python implementation, not a replacement Studio or render backend.

- `app/routers/studio.py` authenticates through the existing middleware, validates messages and ownership, persists them, and queues work. SSE replays persisted Studio events with a sequence cursor.
- `studio_store.py` is canonical PostgreSQL persistence in production; its existing atomic JSON development fallback remains available without a database.
- Lite uses the original `studio_orchestrator.dispatch_message` → original Celery `airender.studio_message` (or original thread fallback) → unchanged `process_message`. Its prompts, intent handling, tools and engine flows remain unchanged.
- `studio_tools.py` is the typed allow-list. Its low-level handlers accept server paths; they must not be exposed directly to an LLM. Medium exposes attachment/project IDs and resolves them under authenticated ownership before calling existing handlers.
- Existing shared helpers construct creative storyboards, apply revisions, approve exact plan versions and synchronize native jobs. Medium uses these capabilities, never Lite's message processor/intent router.
- Existing FFmpeg, captions, Talking, Localize, Content Creator, queues, render progress, output history and Gateway remain responsible for their current work. `hermes/` is not changed.
- Processing/export settings are device-oriented; the new agent preference is separate and persisted by authenticated user. Agent mode is not render mode, manual approval mode, provider, or LLM model.

## Explicit selection and persistence

Display names: **EditorGPT Lite** (`lite`) and **EditorGPT Medium** (`medium`). There is no Auto agent, complexity router, engine fallback or automatic upgrade/downgrade.

Settings → Default Agent Mode applies only to new conversations. Composer selection applies to subsequent submissions and does not change the global preference. The composer snapshots its choice before uploads/navigation. Text, attachments, project, history and outputs are not reset. Switching during a job does not change that execution.

- `GET/PUT /studio/agent-preferences`: database-backed default per authenticated user.
- Conversation `state.agent_mode`: last explicitly selected composer mode. Legacy conversations use Lite.
- `POST /studio/conversations/{id}/messages`: `agent_mode` validates as `lite|medium`. Omitted by an old client means Lite, never content-based inference.
- `studio_messages.agent_mode`: request history; legacy records default to Lite.
- `studio_agent_runs`: immutable engine selection and owner/message association; mutable status, bounded request references, plan, operation ledger, resume decision. Lite records `dispatched`, with its native project/events remaining authoritative for completion.
- `GET /studio/conversations/{id}` includes public `agent_runs` so approval/retry controls survive refresh.
- `POST /studio/agent-runs/{id}/resume` accepts `approve|retry|cancel`; ownership and a status compare-and-set prevent duplicate approvals.

If Medium's dependencies are unavailable, its request fails clearly; no Lite request is substituted. A user may manually choose Lite for another message.

### Gateway readiness and narration

Agent dependency availability does not mean the local Gateway catalog is initialized.
Synchronize the real Gateway model catalog and test the configured route models for
`chat` (planning) and `streaming` (chat narration). Never mark a capability verified
without a successful probe. Preserve operator-selected model order. Enable streaming
on the existing `conversation_response` route to receive real incremental replies.

Medium reuses the shared opening-response stream without invoking Lite orchestration;
successful opening replies are persisted once per execution. Failed openings can be
retried when the user resumes. Completed tool evidence is narrated through the existing
Studio narrator, with Gateway owner/conversation context preserved across its thread.
Planning uses `editing_agent`; user-facing closing messages use `conversation_response`.
All saved Medium messages survive refresh and retain `agent_mode=medium`.

Medium planning uses the Gateway's existing `complete` retry/fallback owner for
both ordinary JSON responses and buffered SSE transport. The validator checks
JSON, EditingPlan schema, tool inputs and conversation-scoped asset/project
ownership **before** a response is audited as successful. Invalid responses are
eligible for the configured provider fallback, including direct JSON fallback.
If those attempts produce only invalid plans, one bounded correction request
includes safe validation feedback. Neither correction nor fallback executes tools
or changes agent engines. Unknown/future project IDs remain rejected; a plan
creating a project must stop before dependent operations and replan from real IDs.

The router requires credentials for each direct endpoint on this installation.
Provider switches without keys do not make a usable provider. Configure secrets
through the admin Direct providers controls or `DIRECT_<PROVIDER>_API_KEY`, not
conversation messages.

Protocol disconnects are transport failures eligible for the existing configured
fallback. If both streaming transports fail **before any content is emitted**, the
same configured route may return an ordinary real model response. This is not simulated
streaming, and never changes agent engines. No replay occurs after a token is emitted.

## Medium graph

Version verified locally: `langgraph==1.2.17`, SQLite checkpoint saver `3.1.2`, PostgreSQL checkpoint saver `3.2.0`. APIs are from the installed official Python packages (`StateGraph`, `interrupt`, `Command`, `get_state`, synchronous durability).

Graph: normalized context → structured plan → approval (for writes) → validated tool → job wait → next step/replan → streamed result. Requests needing only a response/question skip tools. Inspections can run first; later planning uses their actual observations. At most three planning rounds, eight steps per round, recursion limit 50 and a cooperative 15-minute execution budget; existing Gateway/engine timeouts still apply inside operations.

The Gateway's configured `editing_agent` route produces validated structured tool plans and streams the final response. No OpenAI-specific model/client or second provider registry is introduced. Existing Gateway model restrictions, token accounting, configured provider failover and logging continue unchanged. No provider is chosen based on Lite/Medium. External LangSmith tracing is explicitly disabled for these private graph invocations.

Supported adapters:

| Tool | Existing capability | Approval |
| --- | --- | --- |
| `inspect_media` | `studio_tools.execute` / native probe | Read only |
| `inspect_url` | Existing SSRF-protected page reader and chat screenshot attachments | Read only |
| `inspect_project` | Existing native project document/timeline builders | Read only |
| `check_render_status` | Existing engine status handler | Read only |
| `analyze_talking_reel` | Existing Talking analysis and Studio project records | Required |
| `localize_video` | Existing Localize analysis | Required |
| `create_storyboard` | Existing creative direction + storyboard flow | Required; generation retains its native approval |
| `modify_project` | Existing engine-specific validated revision flow | Required |
| `render_approved_plan` | Exact existing Talking plan version approval | Required; stale versions rejected |

Tool arguments reject extra fields, client user IDs, paths and arbitrary commands. Projects must belong to both the user and this conversation. Attachments resolve through the existing ownership-checked repository. Model-proposed URLs must match sources actually supplied by the user (including query parameters), rather than allowing an injected page instruction to create a new outbound destination. Native edit pipelines validate their actual operations; this does not add unsupported editing features.

## Checkpoints and recovery

- Production uses official `PostgresSaver` on the **same configured PostgreSQL database**. No additional service/database.
- No-database local development uses official `SqliteSaver` at `<JOBS_DIR>/studio/medium-checkpoints.sqlite` on the existing persistent jobs volume.
- The internal thread identifier hashes authenticated user + conversation + execution. It is never client-selectable.
- Checkpoints contain bounded context, plan/results and asset/job references, not video binaries, provider keys or a duplicate project database.
- An expensive operation is marked started before execution and completed with its result before progressing. Completed operations are reused after recovery. An ambiguous started write is **not automatically replayed**; the run stops for project inspection, preventing duplicate charges/submissions.
- Approval and job waits use real LangGraph interrupts. No LLM request or Celery worker remains occupied while a render runs. Native workers continue independently of the browser.
- Existing Studio synchronization resumes a waiting graph once the referenced project reaches a stable state. If every client disconnects, the native job still runs; graph continuation is reconciled when Studio reconnects. This version does not add a new continuous graph scheduler.
- A lost executing worker becomes manually resumable after its existing heartbeat disappears (at least 30 seconds). Normal Stop generations are shared with native helpers. Cancellation is cooperative: it cannot interrupt an already transmitted provider request.
- Per-user admission limits Medium to four unfinished executions and twelve new requests/minute; one unfinished Medium run per conversation. PostgreSQL admission and claims serialize across API processes. This does not alter Lite's current queue policy.
- Development JSON persistence inherits the existing single-installation limitations; production multi-process isolation uses PostgreSQL. Back up the jobs volume and database together.

## Deployment

This change was implemented and tested locally. Do not roll it into a running production render without scheduling the existing API/worker deployment procedure.

1. Back up PostgreSQL and the jobs volume. Drain active workers normally.
2. Install the new production lock in the API **and** worker images/environments:

   ```sh
   python -m pip install -r requirements.lock
   ```

3. Run the additive application migration **before starting the new code**:

   ```sh
   python -m alembic upgrade head
   ```

   New head: `0c42e16b873a`, parent `01b9a7d0c123`. It adds preference/run tables and the defaulted message mode column; existing data is preserved.

4. Once, using the same backend environment and database credentials, initialize the official checkpoint schema:

   ```sh
   python -m app.agents.medium.checkpoints
   ```

   PostgreSQL's official saver manages its own versioned checkpoint tables. Setup is intentionally not DDL on every request. Keep the jobs volume mounted for the SQLite development saver.

5. Build the frontend with `cd web && npm ci && npm run build`. Restart API/Celery using the existing deployment. No new always-on service is needed. Old queued Lite `airender.studio_message` jobs remain compatible. New Medium jobs use `airender.studio_agent`.
6. Check `/studio/agent-preferences` authenticated, select Medium in a new chat, inspect its plan, approve once, reconnect, and check output through the existing Preview/Edit UI.

For long-term operations, back up and periodically prune terminal graph checkpoints using the official saver's `delete_thread` method after an explicit retention policy (for example 30 days). Retain native job files and the execution ledger for the required audit period. Do not delete active/interrupted graph threads.

## Rollback

Stop new Medium submissions and drain/cancel its active executions with the normal controls. Redeploy the previous frontend/API/worker version. **Leave the additive schema and checkpoint tables in place** for a non-destructive rollback; older Studio ignores them. Existing rendered files and projects are not changed. Removing the migration with `alembic downgrade 01b9a7d0c123` deletes the new run/preference records and should only be done after a backup and an explicit decision to discard those records. Never downgrade a live graph's schema.

## Verification and limitations

Verified locally on 2026-10-26: **80 relevant Python tests passed**, **77 frontend tests passed**, TypeScript/Vite production build passed, and `pip check` reported no broken requirements. The remaining build notice is the existing large-chunk warning. The local API was restarted with permission; HTTP `localhost:5187`, HTTPS `localhost:5190` and the new preferences endpoint returned 200. A real browser preference was saved, reloaded and used to initialize the new-chat composer, then restored to Lite. No production deployment or paid model/media generation was performed.

- Automated Python tests exercise deterministic dispatch, existing Studio regressions, SQLAlchemy preference/run storage, owner isolation, actual on-disk LangGraph interrupt/recompile/resume, single-use approval, stop, real native media probe, SSE persistence and prevention of ambiguous paid retries. Model/provider calls are replaced **only in tests**, never production.
- Frontend tests include actual Composer/Menu interaction in JSDOM: keyboard selection, unchanged text/attachment, switching while prior work runs, and explicit selected mode on Send. Existing frontend suite and TypeScript/Vite build also run.
- Browser inspection checks the actual local interface at desktop and 320/375px widths. This is responsive browser testing, **not physical iPhone/iPad/Android or installed-PWA hardware testing**.
- A live external AI/video generation or production PostgreSQL/Celery render is not claimed by these offline integration tests. Run a controlled staging media workflow before production rollout.
- Medium orchestrates supported existing tools only. It does not add unrestricted timeline manipulation, shell access, a new render engine, autonomous long-term memory, or guaranteed cancellation of in-flight third-party calls.

## Changed files

Backend: `app/models.py`, `app/studio_store.py`, `app/routers/studio.py`, `app/studio_orchestrator.py`, `app/tasks.py`; new `app/agents/{__init__,store,dispatcher}.py` and `app/agents/medium/{__init__,state,tools,nodes,graph,checkpoints}.py`.

Persistence/dependencies: `alembic/versions/0c42e16b873a_studio_agent_modes.py`, `requirements-prod.txt`, `requirements.lock`.

Frontend: `web/src/api.ts`, `web/src/ui.tsx`, `web/src/Settings.tsx`, `web/src/Studio.tsx`, `web/src/studio/Composer.tsx`, new `web/src/studio/AgentMode.tsx`, `web/src/components/Menu.tsx`, `web/src/styles/studio.css`.

Tests/docs: `tests/test_studio_agents.py`, `web/tests/agent-mode.test.mjs`, this document; `.gitignore` permits the new regression test while retaining the existing test exclusions.

Official references: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), [official repository](https://github.com/langchain-ai/langgraph).

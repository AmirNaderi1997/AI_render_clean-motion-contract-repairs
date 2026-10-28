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

## Pending acceptance gates

Composio Sessions adapter, authenticated UI connections, approved external action
execution, Persian adapters, structured Creative Director handoff and LangGraph
tools are not yet delivered. Installation alone does not activate those paths.
No live account or paid model calls are required for installation tests.

Verified locally: all 13 skills passed native security scans and appear enabled
in `hermes skills list --source hub`; a second installation was a no-op for all
13. Three offline installer contract tests passed. No production changes were made.

Composio implementation must use a stable server-derived user identity and reuse
persisted session IDs. Explicit toolkit allowlists and disabled remote sandbox
tools are required. Discovery is not authorization; every mutation must pass the
existing backend approval contract. API keys stay encrypted server-side.

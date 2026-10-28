# Motion template contract on synced main

Base: fork `main` at `3a5a01e4b7f96818c21176032e0a8d176b6b9d41`.
The v2 repair branch merges `54993cb` without rewriting either old branch.

## Conflicts

- `creative/motion.py`: retain public saved-plan reconstruction and the template-only no-op `compose`; remove the rewritten model scene author, palette author and authored cache reader.
- `engine/hyperframes/scenes.py` (modify/delete): delete the executable scene validator/adapter. Local font helpers live in `fonts.py`; overlay imports those helpers.
- `product_reel.py`: retain main's `fmt`/WebM support and add explicit 30 fps to that same CLI command.
- `quality.py`: retain main's `improve_beats` compatibility function, which returns its input without rewriting it; keep actual-file QC and do not revive semantic rewriting.

## Execution-boundary audit

Command (run at the repository root):

```sh
git grep -n 'custom\["html"\]\|custom\["js"\]\|custom\["css"\]\|author_scene\|validate_scene\|scene_markup\|scene_script'
```

Remaining hits:

- `app/motion_graphic.py`, two calls to `mg.author_scene` in the old worker helpers: the worker is disabled before planning, and `creative.motion_graphic.author_scene` always raises `CreativeUnavailable`. Neither call can produce executable content, including through a cached plan.
- `creative/motion_graphic.py`, the `author_scene` alias to `unavailable`: rejection-only compatibility API.
- `tests/test_scenes.py`, parametrized rejection test: confirms every old code-generation/assembly API raises.

There are no remaining `custom["html"]`, `custom["js"]`, `custom["css"]`, `validate_scene`, `scene_markup` or `scene_script` code paths.

Additional sinks reviewed:

- talking_5 `author_panels`: removed, including all retries and the authored background override. Rendering no longer drops split shots because authoring is unavailable.
- `overlay_reel.build_project`: strips legacy code before serializing `script.json`; converts bounded beat fields to maintained panels. Text uses `html.escape`; registry mounts use quote-escaped JSON attributes. Component IDs and zoom are maintained data, never paths supplied by a model.
- `creative.panel_library`: only `SAFE_COMPONENTS` intersected with manifest and maintained fillers can load. A requested id is honored only if reviewed and compatible; arbitrary component HTML, CSS, JS, values, paths, style and timing fields are discarded. Fillers derive only typed content fields from bounded title/items. Invalid fields fail before the mount.
- `registry_runtime`: the older two supported adapters remain source-hash and license pinned through unchanged `registry_pins.py`. Data inserted into fixed JavaScript/JSON metadata is JSON encoded with `<`, `>`, `&`, apostrophe and Unicode separator escaping. Regex replacements use callbacks so backslashes remain data. The disabled pipeline helper has the same encoding.
- `builder`/`product_reel`: maintained markup and timeline templates, escaped copy, numeric timeline positions, validated identifiers/accent and canonical owned media paths. No authored-code branch.
- `remotion_renderer` and `remotion/src`: owned typed configuration to fixed React components; React text children, no model JSX or `dangerouslySetInnerHTML`.
- creative resource discovery/preview: catalog selection is metadata; native preview uses existing fixed effects/transitions, not authored source. Snapshot fingerprint for the locally repaired registry adapter is updated explicitly; upstream source pins and media quality baselines are unchanged.

## Vendored registry provenance and adapters

All 45 `MANIFEST.json` source byte lengths and SHA-256 hashes match. `NOTICE.md` identifies source commit `3b2058a2b7a2`; the Apache-2.0 license matches SHA-256 `4259155fb06f127687ee7b0a8a3682d45132db0f2da26cbc0b7a2d1e796436b8`. Vendored sources, manifest, notice, license and `registry_pins.py` are unchanged.

The 22-component execution subset excludes per-letter/HTML-string components and fabricated chart/stat fillers. All enabled filler fields are checked against the source's declared content schema. Original files stay intact. A deterministic job-local adapter supplies local GSAP and Ray, RTL, zero tracking and no text transform; receipts record original/adapted hashes and adapter version. No model text enters the adapted component source. Content is delivered through escaped attributes and the reviewed components' textContent sinks.

Every resolved panel records `component` and `template_resolution.reason` in `script.json`. A legacy panel uses the closest compatible component; missing, exhausted or corrupt registry resources use an escaped built-in kinetic/steps/comparison/stat panel. This fallback retains the render and the split shot. It never loads the old authored cache.

## Verification

Fresh fixtures and SHA-256 measurements are recorded in `docs/motion-caption-evidence.md`. These are direct local renderer runs, not a live app/provider acceptance run. App publication/review/error classification is covered by unit tests with fixture renderers and review responses.

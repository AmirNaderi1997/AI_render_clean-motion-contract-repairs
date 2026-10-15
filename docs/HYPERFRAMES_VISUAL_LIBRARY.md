# HyperFrames visual library

AI Render keeps a complete, versioned metadata snapshot of the official
HyperFrames catalog in `engine/hyperframes/catalog_index.json`.  The snapshot
contains every item's name, type, title, description, tags, dimensions,
duration, orientation, provenance and install command.  It is regenerated with:

```bash
.venv/bin/python scripts/sync_hyperframes_catalog.py
```

The same index records the 19 free HTML-native examples published by React
Video Editor.  Those entries are reference-only because they are not part of
the signed HyperFrames registry.

## Runtime safety and quality

`engine.hyperframes.catalog.recommend()` ranks official catalog references for
each visual beat.  Portrait and overlay-friendly items receive preference.
The chosen references are written to the render project's `meta.json`, making
every design decision inspectable and reproducible.

The API does not execute arbitrary remote catalog HTML.  It renders the local,
audited 9:16 adapters in `builder.py`; this preserves Ray typography, RTL text,
speaker framing and deterministic rendering.  Catalog items are therefore a
design vocabulary and provenance layer, not an unsafe plugin mechanism.

Supported talking-reel families are: concept diagram, statistic, comparison,
steps, app/UI showcase, media collage, chat thread, map route, specification
callout, kinetic type and before/after.

## Sources

- https://hyperframes.heygen.com/examples
- https://hyperframes.heygen.com/catalog
- https://github.com/heygen-com/hyperframes
- https://github.com/heygen-com/hyperframes/blob/main/skills/hyperframes-registry/references/templates.md
- https://www.reactvideoeditor.com/hyperframes-templates

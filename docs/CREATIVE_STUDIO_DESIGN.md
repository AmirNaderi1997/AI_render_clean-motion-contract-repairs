# Creative Studio — approval, personalization and timeline editing

Design for the brief "AI proposes. User approves. AI produces. User controls everything."
Grounded in the code as of `968bce8`. Facts first, then the target model, then phases.

## 1. What the code does today

| Area | Today | Gap against the brief |
|---|---|---|
| Approval | Auto mode renders Talking and Localize as soon as analysis is ready (`auto_render` in `sync_conversation`). Manual mode has a single `manual_checkpoint`. Motion has a storyboard confirmation action. | No mandatory gate in Auto mode; no versioned plan; approval is not tied to a plan version. |
| Creative plan | `creative.director` produces brief + 3 concepts + critique + chosen concept, stored as `creative_plan` on the engine state. Only the winner is announced. | Alternatives never reach the user; the plan is not in plain language; no estimate. |
| Personal context | Manual questions ask name, tagline, logo, CTA every time (`studio_manual.begin(..., essentials=True)` in Auto mode too). Nothing is remembered. | No brand profile; repeated questions. |
| Revisions | `creative.revise` turns chat into typed ops on the Talking engine and re-renders the whole video. | Ops are applied straight to the engine, not to a plan or project document. |
| Editing | Talking styles are monolithic FFmpeg renderers driven by sentence-indexed decisions (captions, storyboard, titles, render_settings). The generic Edit Plan (`engine/schema.py`) renders through MLT and is the only timeline-shaped model. | There is no shared project document, no stable element ids across engines, no timeline renderer for Talking output. |

## 2. Target model

One **Project Document** per Studio project is the single source of truth. Chat ops,
the plan review UI and the timeline editor all produce **operations** on it; renderers
consume it through adapters.

```
CreativePlan (versioned, plain language)  ──approve(version)──►  ProjectDocument (versioned)
        ▲ chat ops / manual edits                                     ▲ chat ops / timeline edits
        │                                                             │
   Engine analysis (Talking/Localize/Motion)                 Adapters ──► Renderers
```

Entities (stable ids everywhere): Project, CreativePlan, PlanVersion, StyleProfile/BrandProfile,
Storyboard, Scene, Track, Clip, Element (title/caption/motion/broll/audio), Asset, Effect, Keyframe,
Caption, Translation, AudioSegment, RenderJob, Preview, Revision.

Workflow states (one machine for every engine):
`input_received → analyzing → brief → (style_clarification) → concepts → style_preview → plan_review →
awaiting_approval → approved → asset_preparation → production → draft_rendering → quality_evaluation →
user_review → (revision → plan_review) → final_rendering → completed`.
`awaiting_approval → approved` only through `approve(plan_version_id)` where the id is the current version.
Any edit that changes output creates a new plan version and clears approval.

## 3. Phases

Each phase ships working, tested behaviour end to end; nothing is a UI-only label.

1. **Approval and personalization (this branch).** Versioned Creative Plan for Talking projects built
   from real analysis; mandatory approval in Auto and Manual modes; plan edits by chat and by form, each a
   new version; concept cards with real-frame style mockups (libass, Ray font); brand profile that fills
   plans and is updated from answers, so known values are not asked again. Localize and Motion keep their
   existing gates in this phase.
2. **Project Document + read-only timeline.** Adapters convert Talking/Localize/Motion state into tracks
   and elements with stable ids; the Edit tab shows the real timeline of what was rendered.
3. **Timeline renderer.** A document-driven compositor (MLT, extending `engine/build_mlt.py`) so manual
   edits to clips, titles, captions and audio render for real; Talking styles become document producers.
4. **Element editing.** Captions/on-screen text (drag, font, colour, animation, RTL), B-roll replace and
   regenerate, audio tracks (volume, fades, ducking, single-sentence narration regenerate).
5. **Colour, transform, keyframes, effects.** Only properties both Preview and Render implement.
6. **Previews and partial re-render.** Motion previews of a few seconds, per-scene/element cache, render
   only changed ranges; Fast vs Premium production per scene with a real cost/time estimate.

## 4. Honesty rules carried over

No invented progress, cost or capability. Mockups are labelled as concept mockups, never as output.
A flattened clip (Motion.so) is shown as not internally editable. Unknown cost is shown as unknown.

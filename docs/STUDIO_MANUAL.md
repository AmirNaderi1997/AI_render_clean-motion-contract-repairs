# Studio Manual mode

The hand next to Send toggles Auto/Manual. Auto remains the default; existing
cost/retry confirmations still apply. Mode is persisted in conversation state.
Changing mode never starts work or cancels a running engine. An already pending
render approval must still be resolved explicitly.

Manual uses the existing engines, repository, SSE and attachment ownership checks:

- Talking: real style registry → grade → installed caption font → title accent →
  logo animation, optional logo image and tint → CTA → optional style reference →
  analysis approval → real hook/storyboard review and edits → render approval.
- Localize: supported caption box → end card → analysis approval → translation
  review/edits → dubbing and render approval.
- Motion: visual brief → optional reference → analysis/storyboard approval →
  existing generation confirmation → final render confirmation when assets are ready.

Analysis includes the engine's internal transcription, creative planning and
storyboard work as one disclosed stage. Asset generation and narration likewise
remain the existing combined generation operation, not independent per-scene
approvals. This feature does not expose a toggle for every internal tool call.
No progress or media is fabricated. Choices are capabilities that the existing
engines can execute; native Talking delivery remains 9:16.

References are explicitly designated image/video attachments, separate from source
footage, product images and logo files. Video references are sampled at three
points, not analyzed as continuous motion. Vision guidance is fed into the approved
creative request through the existing gateway. Exact/pixel-identical copying is
not promised. Failed vision never silently claims a reference was understood.

Each active question has a changing opaque ID. Answers and render approvals are
single-use, owner-scoped and row-locked in PostgreSQL (locked JSON in local mode).
The render gate survives refresh and SSE reconnect. Resume cannot bypass it.
No database migration, new provider, secret or dependency is required.

Verification: unit/integration tests in `tests/test_studio_manual.py`, existing
caption/layout tests, frontend tests, TypeScript/Vite build, and a local UI → API →
persisted question → next question → refresh test. Verification stops before paid
analysis, asset generation, narration or rendering. Browser extension file upload
may require the user's own “Allow access to file URLs” setting; the agent must not
weaken that protection automatically.

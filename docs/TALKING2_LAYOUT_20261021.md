# Talking 2: continuous explanatory split

User-approved output remains 1080×1920 (9:16), not two exact square frames.

- Native face-aware speaker crop fills the bottom half; no whole-video PiP scaling.
- Native Persian ASS hook/captions sit at y=960 on a 1080px-wide backed rail (y=888..1032). Talking 1/3/4 keep their own caption integrations.
- Kept transcript sentences form contiguous groups of five (a one-sentence tail is redistributed). Each group's exact source indices and full text reach the motion author. Dropped speech is excluded; source timing is mapped through actual cuts.
- The graphics-only browser composition is 1080×888. It cannot move the speaker or paint over the caption rail. Native FFmpeg combines the layers and restores one continuous source audio clock.
- Missing authored panels and failed visual checks stop explicitly; no silent template downgrade or automatic template-rotation render retry.
- Screenshot attachments on an existing project resolve to a revision, not a fresh source upload. A genuinely new video can still start a new edit.
- Cache identities include scene content, geometry and direction; previous exports are preserved.

Verification: deterministic contract tests; an actual 3-second native FFmpeg/libass export with audio; an actual 3-second HyperFrames browser panel plus FFmpeg composition, full decode and painted-pixel checks. These synthetic fixtures prove wiring/geometry/Persian shaping, not creative quality of the full customer video. No paid media generation was used for these tests. Full-project visual acceptance is separate.

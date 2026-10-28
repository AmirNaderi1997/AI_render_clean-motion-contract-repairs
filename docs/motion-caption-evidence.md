# Motion and caption fixture evidence

## v2 contract repairs on synced main, 2026-10-28

Base `3a5a01e`; fresh direct local renders with HyperFrames 0.8.161, Remotion 4.0.536, local headless Chrome and local Ray. No provider requests, production app run or deployment. The talking_2 input intentionally has 25 fps to check delivery conversion. The talking_5 fixture includes a legacy authored payload and resolves to `headline-slam`; the payload is absent from generated sources.

Full Python suite: **702 passed, 10 skipped**. Frontend: **92 passed**, zero skips; production build passed. A fixed 30 ms wait in the inherited resource-editor test raced async catalog loading under concurrent tests/renders; it now waits up to 2 seconds for the catalog element.

Skipped: Composio SDK contract (2, optional `composio` absent), libass-dependent creative-plan/motion.so (4, host FFmpeg has no libass), face effects (1, optional mediapipe absent), opt-in talking_2 integrations (2), opt-in tscaps end-to-end (1). Direct renderer fixtures below ran separately; these do not exercise the skipped whole-app/matte/tscaps integrations.

All four exports are **1080×1920, 30/1 fps, 90 frames, 3.000 seconds**. Each passes full FFmpeg decode and `quality.review_render` with no problems, unavailable results or warnings. Frame sheets sample 0.20, 0.80, 1.50 and 2.60 seconds. Visual inspection confirms joined Persian, RTL, Persian scene counters, the talking_2 lower region preserved and the talking_5 upper template visible. The product and overlay are visual-only fixtures; talking_2 carries synthetic audio. No human voice/caption listening claim is made.

- `product-reel.mp4`: SHA-256 `564020348b6577af80a472ac8e2424f0b52a8e7132a0fba7c3a21b955c165321`. Local media `/tmp/motion-v2-pr1-fixtures/product-reel.mp4`; frame sheet `/tmp/motion-v2-pr1-fixtures/product-reel.mp4-sheet.png`.
- `remotion-reel.mp4`: SHA-256 `beb621404854fb286b521ff440401b49fc7f2b2a8d2adf044c3e5f2438863017`. Local media `/tmp/motion-v2-pr1-fixtures/remotion-reel.mp4`; frame sheet `/tmp/motion-v2-pr1-fixtures/remotion-reel.mp4-sheet.png`.
- `talking2-template.mp4`: SHA-256 `fdef3b8d6959feacf5bf5098122d281c7d154566d27147e378f75cb8d75a92d9`. Local media `/tmp/motion-v2-pr1-fixtures/talking2-template.mp4`; frame sheet `/tmp/motion-v2-pr1-fixtures/talking2-template.mp4-sheet.png`.
- `talking5-overlay.mp4`: SHA-256 `7f246fd004778e9dc7be6778534fa69788e0a472fb324117579e63b508492c8d`. Local media `/tmp/motion-v2-pr1-fixtures/talking5-overlay.mp4`; frame sheet `/tmp/motion-v2-pr1-fixtures/talking5-overlay.mp4-sheet.png`.

Media, frame sheets, ffprobe data and test logs stay outside Git. PR descriptions carry the fixture references. This document records measurements and hashes only.

## v2 caption stack, 2026-10-28

Re-applied `42dcde8` on v2 contract repairs and added the unsupported-timestamps
fallback. Full Python suite: **731 passed, 10 skipped** (same reasons above).
Frontend: **92 passed**, zero skipped; production build passed. Provider tests
mock HTTP/STT. Cases cover 404/405/501 and unsupported 400/422, generation of
plain narration on the same relay/voice/model, content-hash STT cache reuse,
missing/malformed metadata, and no retry of 401/402/429/500. No provider request
or production app run is claimed.

Freshly rendered all four direct fixtures on the caption branch. All remain
1080×1920, 30/1 fps, 90 frames, 3.000 seconds, complete-decode passed and
`quality.review_render` passed with no problems, warnings or unavailable findings.
Frame sheets at 0.20/0.80/1.50/2.60s were inspected. Paths are under
`/tmp/motion-v2-pr2-fixtures/`:

- `product-reel.mp4`: SHA-256 `9b84693875fdb00c01e8135308252b7d49fb826dcb0b8cf6097018cf369d2686`; frame sheet `product-reel.mp4-sheet.png`.
- `remotion-reel.mp4`: SHA-256 `beb621404854fb286b521ff440401b49fc7f2b2a8d2adf044c3e5f2438863017`; frame sheet `remotion-reel.mp4-sheet.png`.
- `talking2-template.mp4`: SHA-256 `fdef3b8d6959feacf5bf5098122d281c7d154566d27147e378f75cb8d75a92d9`; frame sheet `talking2-template.mp4-sheet.png`.
- `talking5-overlay.mp4`: SHA-256 `7f246fd004778e9dc7be6778534fa69788e0a472fb324117579e63b508492c8d`; frame sheet `talking5-overlay.mp4-sheet.png`.

The separate narrated caption fixture ran via:

```sh
python scripts/product_caption_fixture.py --output /tmp/motion-v2-pr2-captions --gsap /tmp/motion-contract-hf/node_modules/gsap/dist/gsap.min.js
```

It uses local macOS Majed isolated spoken words and mocked ElevenLabs STT
boundaries. One mocked STT call serves two identical scenes and a rerender through
the content-hash cache. No live provider calls. Both engines include audio and
pass full decode, 1080×1920 and 30/1 fps. The expected video is 282 frames,
9.400 seconds; the Remotion container reports 9.408 seconds due to audio padding.
The decoded frame sheet `word-changes.png` was inspected: joined RTL Persian,
expected word and page changes at frames immediately before/on/after onset.

- `product-reel.mp4`: SHA-256 `dfe9836d4a209a8b96484a7a5124392466f5a79a842df7c843e21e9a62e28dad`; container duration 9.400000 s.
  - At 1.019750 s, first highlight frame 31; error 13.583 ms (within one 33.333 ms frame). Accent pixel counts before/on/after: [0, 4023, 8025].
  - At 8.416833 s, first highlight frame 253; error 16.500 ms (within one 33.333 ms frame). Accent pixel counts before/on/after: [0, 4139, 7771].
- `remotion-reel.mp4`: SHA-256 `8663e5324fcd50c78abf17d0411d5167f856cb805b808f5634d93278f75f2c85`; container duration 9.408000 s.
  - At 1.019750 s, first highlight frame 31; error 13.583 ms (within one 33.333 ms frame). Accent pixel counts before/on/after: [0, 5760, 6098].
  - At 8.416833 s, first highlight frame 253; error 16.500 ms (within one 33.333 ms frame). Accent pixel counts before/on/after: [0, 5342, 5620].

No binaries, ffprobe dumps, frame-sheet images or generated logs are committed.
App publication and estimated-caption holds are unit tests with mocked renderers;
these direct renderer fixtures do not establish a served end-to-end app run,
live relay capability, natural-sentence ASR quality, pronunciation or human
listening acceptance. The 22 enabled registry adapters are source/sink/field
reviewed; this task's fresh talking_5 render covers `headline-slam`, not a render
matrix of all 22 components.

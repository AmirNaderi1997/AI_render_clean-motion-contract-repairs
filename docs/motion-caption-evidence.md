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

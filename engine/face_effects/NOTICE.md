# Video effects: third-party code and assets

`_fx.py` is adapted from **claude-video-effects** by Vibha Ramprakash (https://github.com/Vibha-Ramprakash/claude-video-effects, `scripts/fx.py`),
MIT licence, Copyright (c) 2026 Vibha Ramprakash. The licence text is in `LICENSE.upstream`.

Changes made for EditorGPT (everything else is upstream code):
- assets are read from `assets/effects/` (`EFFECTS_ASSETS`) instead of the folder next to the script;
- Persian text uses Vazirmatn with raqm shaping whenever a text contains Arabic-script letters (`has_arabic`);
- `locked-on` has no English default label; `swipe` labels default to Persian (قبل / بعد) and can be set with `before` / `after`;
- the tracker stubs two modules mediapipe imports but never uses here (matplotlib, sounddevice);
- `read_frames` can read a window (`ss`, `t`) so only the stretches that carry an effect are processed (`runner.py`).

Bundled with it (`assets/effects/`):
- fonts: Archivo Black, Instrument Serif, Space Mono, Inter, Anton, Montserrat, Playfair Display (SIL OFL 1.1), Permanent Marker (Apache 2.0), Vazirmatn (SIL OFL 1.1); licence files are next to the fonts;
- `models/yunet.onnx`: YuNet face detector from OpenCV Zoo (MIT); `models/selfie_segmenter.tflite`: MediaPipe Selfie Segmenter (Apache 2.0);
- `lib/libGLESv2.so.2`, `lib/libGLdispatch.so.0`: libglvnd 1.7.0 (MIT-style licence), needed by the mediapipe shared library on a slim server image.

Runtime: `mediapipe` (Apache 2.0), installed from wheels with `scripts/fetch_effects_wheels.sh`.

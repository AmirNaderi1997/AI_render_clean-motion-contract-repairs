"""Sarovi Persian text plus offline MMS alignment; no automatic hosted retries."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path

MODEL = "google/gemini-4-argon"
REVISION = "2100fb247d8e43962eef24491597fbeb8b469531"
PROMPT = (
    "Transcribe this Persian audio verbatim. Keep colloquial spoken forms exactly as spoken "
    "(for example می‌خوام and نیستش). Write numbers as spoken words. "
    "Output only the Persian transcript: no summary, commentary, or translation."
)


class RejectedTranscript(RuntimeError):
    """Only fixed, non-sensitive reason codes may be persisted."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def enabled():
    return os.environ.get("SAROVI_TRANSCRIBE_ENABLED", "false").strip().lower() not in {
        "false",
        "0",
        "off",
        "no",
    }


def model_id():
    return os.environ.get("SAROVI_TRANSCRIBE_MODEL", MODEL).strip()


def cache_key(digest, language):
    return hashlib.sha256(
        json.dumps(
            [digest, language, model_id(), REVISION, "gemini_aligned_v1"]
        ).encode()
    ).hexdigest()[:16]


def chunk_boundaries(duration, silences, limit=300.0):
    """Cut at silence midpoints; refuse continuous speech exceeding the limit."""
    cuts = [0.0]
    while duration - cuts[-1] > limit:
        candidates = [
            (a + b) / 2
            for a, b in silences
            if cuts[-1] + 1 < (a + b) / 2 <= cuts[-1] + limit
        ]
        if not candidates:
            raise RejectedTranscript("no_safe_chunk_boundary")
        cuts.append(max(candidates))
    return list(zip(cuts, cuts[1:] + [duration]))


def validate(text, words, duration, reference):
    letters = [c for c in text if c.isalpha()]
    if (
        not letters
        or sum("\u0600" <= c <= "\u06ff" for c in letters) / len(letters) < 0.7
    ):
        raise RejectedTranscript("text_not_persian")
    previous = 0.0
    for w in words:
        a, b = w["start"], w["end"]
        if not (
            math.isfinite(a)
            and math.isfinite(b)
            and previous <= a < b <= duration
            and b - a <= 3
        ):
            raise RejectedTranscript("implausible_word_timing")
        previous = b - 0.001
    share = len(words) / max(1, len(text.split()))
    if share < 0.9 or share > 1:
        raise RejectedTranscript("alignment_coverage_below_90_percent")
    if not reference:
        raise RejectedTranscript("whisper_reference_empty")
    for minute in range(math.ceil(duration / 60)):
        low, high = minute * 60, (minute + 1) * 60
        count = sum(low <= w["start"] < high for w in words)
        expected = sum(low <= w["start"] < high for w in reference)
        if max(count, expected) >= 8 and (
            not count or not expected or not 0.5 <= count / expected <= 2
        ):
            raise RejectedTranscript("per_minute_word_count_mismatch")
    # Measure uncovered speech, not silent wall-clock gaps. Merge nearby Whisper
    # word intervals, then subtract aligned intervals from each speech region.
    regions = []
    for w in reference:
        if regions and w["start"] - regions[-1][1] <= 0.5:
            regions[-1][1] = max(regions[-1][1], w["end"])
        else:
            regions.append([w["start"], w["end"]])
    for a, b in regions:
        cursor = a
        for w in words:
            if w["end"] <= cursor or w["start"] >= b:
                continue
            if w["start"] - cursor > 5:
                raise RejectedTranscript("uncovered_speech_over_5_seconds")
            cursor = max(cursor, w["end"])
        if b - cursor > 5:
            raise RejectedTranscript("uncovered_speech_over_5_seconds")
    return share


def whisper_reference(audio):
    from faster_whisper import WhisperModel
    from brain.transcribe import _whisper_timeout, _whisper_timeout_seconds

    root = Path(
        os.environ.get("WHISPER_LOCAL_MODELS_DIR", "/root/.cache/editor-whisper")
    )
    name = os.environ.get("WHISPER_MODEL_SIZE", "small")
    if not (root / name / "model.bin").is_file():
        raise RejectedTranscript("whisper_reference_cache_missing")
    with _whisper_timeout(_whisper_timeout_seconds()):
        model = WhisperModel(
            str(root / name),
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            local_files_only=True,
        )
        segments, _ = model.transcribe(
            audio, language="fa", beam_size=1, word_timestamps=True, vad_filter=True
        )
        return [
            {"w": w.word, "start": w.start, "end": w.end}
            for s in segments
            for w in (s.words or [])
        ]


def hosted(wav):
    from brain import lm_direct
    from brain.lm_gateway import audio_attempt

    provider = next((p for p in lm_direct.usable() if p["id"] == "sarovi"), None)
    if provider is None:
        raise RejectedTranscript("sarovi_not_configured")
    provider = {**provider, "prefer_stream": False, "format": "openai"}
    with audio_attempt(
        "transcription", "sarovi", model_id(), "chat/completions"
    ) as audit:
        result = lm_direct.call(
            provider,
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(wav).decode(),
                                "format": "wav",
                            },
                        },
                    ],
                }
            ],
            model=model_id(),
            tokens=8192,
            temperature=0,
            timeout=240,
        )
        audit["http_status"] = 200
    choice = result["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise RejectedTranscript("hosted_transcript_truncated")
    cost = result.get("usage", {}).get("cost")
    return choice["message"]["content"].strip(), cost


def transcribe_gemini(video, out_dir, *, language, file_digest):
    import numpy as np
    from brain.mms_alignment import align, preflight

    cache = os.environ.get("MMS_ALIGN_CACHE_DIR", "/root/.cache/mms-align")
    key = cache_key(file_digest, language)
    archive = out_dir / "transcripts" / f"{key}.json"
    if archive.exists():
        result = json.loads(archive.read_text())
        return result, 0.0
    try:
        preflight(cache)
    except FileNotFoundError:
        raise RejectedTranscript("aligner_cache_missing") from None
    if language not in (None, "fa", "fas", "persian"):
        raise RejectedTranscript("language_not_persian")
    with tempfile.TemporaryDirectory(prefix="gemini-asr-", dir=out_dir) as tmp:
        audio_path = Path(tmp) / "audio.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(video),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            timeout=600,
        )
        with wave.open(str(audio_path)) as f:
            duration = f.getnframes() / 16000
        silence = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i",
                str(audio_path),
                "-af",
                "silencedetect=noise=-35dB:d=0.35",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        starts = re.findall(r"silence_start: ([0-9.]+)", silence.stderr)
        ends = re.findall(r"silence_end: ([0-9.]+)", silence.stderr)
        spans = list(zip(map(float, starts), map(float, ends)))
        boundaries = chunk_boundaries(duration, spans)
        words, texts, costs, shares = [], [], [], []
        for index, (a, b) in enumerate(boundaries):
            with wave.open(str(audio_path)) as source:
                source.setpos(round(a * 16000))
                samples = source.readframes(round(b * 16000) - round(a * 16000))
            # Release the Whisper model before loading the MMS session.
            reference = whisper_reference(
                np.frombuffer(samples, dtype="<i2").astype(np.float32) / 32768
            )
            buf = io.BytesIO()
            with wave.open(buf, "wb") as f:
                f.setnchannels(1)
                f.setsampwidth(2)
                f.setframerate(16000)
                f.writeframes(samples)
            chunk = Path(tmp) / "chunk.wav"
            chunk.write_bytes(buf.getvalue())
            # Persist every successful paid response before alignment, including cost
            # if alignment subsequently fails. No automatic hosted replay.
            response_path = out_dir / "transcripts" / f"{key}-chunk-{index}.json"
            if response_path.exists():
                saved = json.loads(response_path.read_text())
                text = saved["text"]
                cost = saved["cost"]
            else:
                pending = response_path.with_suffix(".pending")
                pending.parent.mkdir(exist_ok=True)
                try:
                    with pending.open("x") as marker:
                        marker.write(
                            "Hosted call started; do not automatically replay."
                        )
                except FileExistsError:
                    raise RejectedTranscript(
                        "hosted_outcome_uncertain_no_retry"
                    ) from None
                text, cost = hosted(buf.getvalue())
                response_path.parent.mkdir(exist_ok=True)
                response_path.write_text(
                    json.dumps({"text": text, "cost": cost}, ensure_ascii=False)
                )
            costs.append(cost)
            (out_dir / "asr_gemini_cost.json").write_text(
                json.dumps(
                    {
                        "engine": "gemini_aligned",
                        "cost_usd": (
                            sum(costs)
                            if all(isinstance(c, (int, float)) for c in costs)
                            else None
                        ),
                        "chunks": len(costs),
                    }
                )
            )
            letters = [c for c in text if c.isalpha()]
            if (
                not letters
                or sum("\u0600" <= c <= "\u06ff" for c in letters) / len(letters) < 0.7
            ):
                raise RejectedTranscript("text_not_persian")
            try:
                aligned = align(chunk, text, cache)
            except (ValueError, RuntimeError):
                raise RejectedTranscript("alignment_failed") from None
            shares.append(validate(text, aligned, len(samples) / 32000, reference))
            words.extend(
                {**w, "start": round(w["start"] + a, 3), "end": round(w["end"] + a, 3)}
                for w in aligned
            )
            texts.append(text)
        sentences = []
        for i in range(0, len(words), 12):
            group = words[i : i + 12]
            sentences.append(
                {
                    "text": " ".join(w["w"] for w in group),
                    "start": group[0]["start"],
                    "end": group[-1]["end"],
                }
            )
        result = {
            "engine": "gemini_aligned",
            "model_id": model_id(),
            "file_hash": file_digest,
            "cache_key": key,
            "requested_language": language,
            "language": "fa",
            "duration": duration,
            "words": words,
            "sentences": sentences,
            "alignment_share": min(shares),
            "aligner_revision": REVISION,
        }
        archive.parent.mkdir(exist_ok=True)
        archive.write_text(json.dumps(result, ensure_ascii=False))
        return result, (
            sum(costs) if all(isinstance(c, (int, float)) for c in costs) else None
        )

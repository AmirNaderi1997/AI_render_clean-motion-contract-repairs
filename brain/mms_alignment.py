"""Offline MMS ONNX CTC alignment. Model files must be provisioned separately."""

import json
import wave
from pathlib import Path


def align(audio_path: Path, text: str, cache: str) -> list[dict]:
    preflight(cache)
    import numpy as np
    import onnxruntime as ort
    import uroman

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 2
    opts.inter_op_num_threads = 1
    session = ort.InferenceSession(
        cache + "/model_quantized.onnx",
        sess_options=opts,
        providers=["CPUExecutionProvider"],
    )
    vocab = json.load(open(cache + "/vocab.json"))
    words = text.split()
    roman = uroman.Uroman()
    tokens = []
    owners = []
    for i, w in enumerate(words):
        for c in roman.romanize_string(w):
            if c in vocab and c not in (" ", "*"):
                tokens.append(vocab[c])
                owners.append(i)
    with wave.open(str(audio_path)) as f:
        audio = (
            np.frombuffer(f.readframes(f.getnframes()), dtype="<i2").astype(np.float32)
            / 32768
        )
    if len(audio) > 16000 * 300 or not tokens:
        raise ValueError("alignment_input_limit")
    emissions = []
    times = []
    for offset in range(0, len(audio), 16000 * 15):
        chunk = audio[offset : offset + 16000 * 15]
        feed = {"input_values": chunk[None, :]}
        for inp in session.get_inputs():
            if inp.name == "attention_mask":
                feed[inp.name] = np.ones((1, len(chunk)), dtype=np.int64)
        logits = session.run(None, feed)[0][0]
        logits -= logits.max(axis=-1, keepdims=True)
        logits -= np.log(np.exp(logits).sum(axis=-1, keepdims=True))
        emissions.append(logits)
        times.extend(
            offset / 16000
            + (np.arange(len(logits)) + 0.5) * len(chunk) / 16000 / len(logits)
        )
    em = np.concatenate(emissions)
    blank = vocab["<blank>"]
    states = np.full(2 * len(tokens) + 1, blank)
    states[1::2] = tokens
    skip = np.zeros(len(states), bool)
    skip[2:] = (states[2:] != blank) & (states[2:] != states[:-2])
    if len(em) * len(states) > 100_000_000:
        raise ValueError("alignment_trellis_limit")
    prev = np.full(len(states), -np.inf)
    prev[0] = 0
    back = np.zeros((len(em), len(states)), np.uint8)
    for t, row in enumerate(em):
        choices = np.stack(
            [prev, np.r_[-np.inf, prev[:-1]], np.r_[-np.inf, -np.inf, prev[:-2]]]
        )
        choices[2, ~skip] = -np.inf
        best = choices.argmax(axis=0)
        back[t] = best
        prev = choices[best, np.arange(len(states))] + row[states]
    s = len(states) - 1 if prev[-1] > prev[-2] else len(states) - 2
    if not np.isfinite(prev[s]):
        raise ValueError("alignment_no_path")
    frames = {}
    for t in range(len(em) - 1, -1, -1):
        if s % 2:
            frames.setdefault((s - 1) // 2, []).append(t)
        s -= int(back[t, s])
    result = []
    for i, w in enumerate(words):
        fs = [f for j, o in enumerate(owners) if o == i for f in frames.get(j, [])]
        if fs:
            result.append(
                {
                    "w": w,
                    "start": round(float(times[min(fs)]), 3),
                    "end": min(
                        len(audio) / 16000, round(float(times[max(fs)]) + 0.02, 3)
                    ),
                }
            )
    return result


def preflight(cache: str) -> None:
    """Never download weights on the request path."""
    for name in ("model_quantized.onnx", "vocab.json"):
        if not (Path(cache) / name).is_file():
            raise FileNotFoundError("MMS alignment cache missing: " + name)
    vocab = json.loads((Path(cache) / "vocab.json").read_text())
    if vocab.get("<blank>") != 0:
        raise ValueError("MMS vocabulary requires blank id 0")

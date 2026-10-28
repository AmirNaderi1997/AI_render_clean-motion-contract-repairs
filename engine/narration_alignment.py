"""Speech timing for maintained product templates; never use ASR spelling on screen."""
from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

VERSION = 1


def audio_hash(audio: Path) -> str:
    digest = hashlib.sha256()
    with audio.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def sidecar(audio: Path) -> Path:
    return Path(str(audio) + '.words.json')


def character_words(alignment: dict) -> list[dict]:
    """ElevenLabs original character alignment to words, retaining real boundaries."""
    chars = alignment['characters']
    starts = alignment['character_start_times_seconds']
    ends = alignment['character_end_times_seconds']
    if not (len(chars) == len(starts) == len(ends)):
        raise ValueError('Character alignment lengths differ')
    words, current = [], []
    for char, start, end in zip(chars, starts, ends):
        if char.isspace():
            if current:
                words.append({'w': ''.join(c[0] for c in current), 'start': current[0][1], 'end': current[-1][2]})
                current = []
        else:
            current.append((char, start, end))
    if current:
        words.append({'w': ''.join(c[0] for c in current), 'start': current[0][1], 'end': current[-1][2]})
    return words


def save_tts_words(audio: Path, alignment: dict) -> None:
    words = character_words(alignment)
    # Validate all timings before persisting; scene bounds are checked at render time.
    _validate(words, math.inf)
    sidecar(audio).write_text(json.dumps({'version': VERSION, 'audio_sha256': audio_hash(audio),
        'source': 'elevenlabs_tts', 'words': words}, ensure_ascii=False), encoding='utf-8')


def _normal(text: str) -> str:
    text = text.translate(str.maketrans('يكى٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', 'یکی01234567890123456789'))
    return ''.join(c.lower() for c in text if unicodedata.category(c)[0] in 'LN')


def _validate(words: list[dict], duration: float) -> None:
    previous = 0.0
    if not words:
        raise ValueError('No timed words')
    for word in words:
        start, end = float(word['start']), float(word['end'])
        if not (math.isfinite(start) and math.isfinite(end) and previous <= start < end <= duration):
            raise ValueError('Invalid, overlapping or out-of-scene word times')
        if not _normal(word['w']):
            raise ValueError('Empty spoken word')
        previous = end


def map_script(text: str, words: list[dict], duration: float) -> list[dict]:
    """Map normalized character spans, including ASR split/merged tokens, to script words.

    Refuse omitted/inserted words or substantial spelling drift. Ambiguous content
    stays estimated rather than claiming that guessed boundaries are aligned.
    """
    _validate(words, duration)
    script = text.split()
    tokens = [_normal(w) for w in script]
    if not all(tokens):
        raise ValueError('Script contains an untimed punctuation-only token')
    expected = ''.join(tokens)
    heard, owners = '', []
    for index, word in enumerate(words):
        token = _normal(word['w'])
        heard += token
        owners.extend([index] * len(token))
    match = SequenceMatcher(None, expected, heard, autojunk=False)
    if match.ratio() < .88:
        raise ValueError('Narration differs from script')
    positions = {}
    for tag, a, b, c, d in match.get_opcodes():
        if tag == 'equal':
            positions.update({a + n: c + n for n in range(b - a)})
        elif tag == 'replace' and b - a == d - c:
            positions.update({a + n: c + n for n in range(b - a)})
        else:
            # Deletions/insertions may be missing speech, not spelling. Never interpolate.
            raise ValueError('Script and speech have unmatched content')
    mapped, cursor = [], 0
    for word, token in zip(script, tokens):
        first, last = owners[positions[cursor]], owners[positions[cursor + len(token) - 1]]
        spoken = heard[positions[cursor]:positions[cursor + len(token) - 1] + 1]
        if SequenceMatcher(None, token, spoken, autojunk=False).ratio() < .65:
            raise ValueError('Unmatched script word')
        if any(c.isdigit() for c in token + spoken) and token != spoken:
            raise ValueError('Spoken number differs from script')
        mapped.append({'w': word, 'start': float(words[first]['start']), 'end': float(words[last]['end'])})
        cursor += len(token)
    # A script split inside one ASR token has no measured boundary: hold it.
    _validate(mapped, duration)
    return mapped


def resolve(audio: Path, text: str, duration: float, job_dir: Path) -> tuple[list[dict], str]:
    digest = audio_hash(audio)
    cached = sidecar(audio)
    if cached.is_file():
        try:
            data = json.loads(cached.read_text())
            if data.get('version') == VERSION and data.get('audio_sha256') == digest:
                return map_script(text, data['words'], duration), data['source']
        except (ValueError, KeyError, TypeError):
            pass
    # One private directory per content hash prevents extraction-file collisions.
    directory = job_dir / 'narration_alignment' / digest
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / 'words.json'
    if archive.is_file():
        data = json.loads(archive.read_text())
    else:
        from brain.transcribe_elevenlabs import transcribe_elevenlabs
        transcript, _ = transcribe_elevenlabs(audio, directory, language='fa', file_digest=digest)
        data = {'version': VERSION, 'audio_sha256': digest, 'source': 'elevenlabs_stt', 'words': transcript['words']}
        _validate(data['words'], math.inf)
        archive.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    return map_script(text, data['words'], duration), data['source']


def prepare(config: dict, job_dir: Path) -> tuple[dict, dict]:
    """Called once by the job before engine fallback; direct adapters also use it."""
    from engine.motion_contract import validate_motion_config
    config = validate_motion_config(config, job_dir)
    evidence = []
    for index, scene in enumerate(config['scenes']):
        text = str(scene.get('narration_text') or '')
        scene['caption_words'] = []
        if not text.strip():
            scene['caption_timing'] = 'none'
            evidence.append({'scene': index, 'caption_timing': 'none'})
            continue
        try:
            if not scene.get('narration'):
                raise ValueError('Narration audio is missing')
            scene['caption_words'], source = resolve(Path(scene['narration']), text, scene['frames'] / 30, job_dir)
            scene['caption_timing'] = 'aligned'
            evidence.append({'scene': index, 'caption_timing': 'aligned', 'source': source,
                             'words': scene['caption_words'], 'audio_sha256': audio_hash(Path(scene['narration']))})
        except Exception as exc:
            scene['caption_timing'] = 'estimated'
            # Do not persist provider exception text, which may contain credentials.
            evidence.append({'scene': index, 'caption_timing': 'estimated', 'reason': type(exc).__name__})
    timing = 'estimated' if any(e['caption_timing'] == 'estimated' for e in evidence) else (
        'aligned' if any(e['caption_timing'] == 'aligned' for e in evidence) else 'none')
    report = {'caption_timing': timing, 'scenes': evidence}
    (job_dir / 'caption_timing.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return config, report

"""Offline audio routing contracts. No real credentials, media jobs or paid calls."""
import base64
import json
from pathlib import Path

import httpx
import pytest

from brain import lm_direct as direct, lm_gateway as gateway, tts, transcribe
from brain import transcribe_elevenlabs as stt, speech_policy

AUDIO = b'ID3' + b'x' * 2048
WORDS = [{'word': 'سلام', 'start': 0.0, 'end': 0.8}]


@pytest.fixture(autouse=True)
def isolated_audio(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_PROXY_URL', '')
    monkeypatch.setenv('SAROVI_STT_ENABLED', 'true')
    monkeypatch.delenv('NARRATION_TTS_ORDER', raising=False)
    monkeypatch.delenv('SAROVI_STT_FORMAT', raising=False)
    monkeypatch.delenv('SAROVI_ELEVENLABS_VOICE', raising=False)
    monkeypatch.setenv('WHISPER_ENABLED', 'true')
    for pid in ('jarvis', 'sarovi'):
        monkeypatch.setenv(pid.upper() + '_API_KEY', 'secret-' + pid)
    monkeypatch.setattr(gateway, '_audit', lambda record: None)


def providers():
    return {p['id']: p for p in direct.config()['providers']}


def response(pid, data=None):
    if pid == 'sarovi':
        return httpx.Response(200, json=data or {'output': {'mediaType': 'audio/mpeg', 'data': base64.b64encode(AUDIO).decode()}})
    return httpx.Response(200, content=AUDIO, headers={'content-type': 'audio/mpeg'})


@pytest.mark.parametrize('failure', ['timeout', '500', 'bad_audio'])
def test_tts_order_one_attempt_per_provider_and_audit(monkeypatch, failure):
    seen, rows = [], []
    monkeypatch.setenv('NARRATION_TTS_ORDER', direct.DEFAULT_NARRATION_TTS_ORDER + ',jarvis:TTS_ELEVEN_V4')
    monkeypatch.setattr(gateway, '_audit', rows.append)
    def post(request):
        pid = 'jarvis' if request.url.host == 'api.jarvis.you' else 'sarovi'
        seen.append(pid)
        payload = json.loads(request.content)
        if pid == 'jarvis':
            assert payload['voice'] == 'configured-voice-id'
            assert payload['input'] == 'این آزمایش است' and payload['response_format'] == 'mp3'
            if failure == 'timeout':
                raise httpx.ReadTimeout('secret-jarvis')
            if failure == '500':
                return httpx.Response(500, text='secret-jarvis')
            return httpx.Response(200, text='secret-jarvis')
        assert request.url.path == '/v1/studio/audio'
        assert payload['voice'] == 'george' and payload['format'] == 'mp3'
        return response(pid)
    original = httpx.Client
    monkeypatch.setattr(direct.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(post), **kw))
    result = direct.narration('این آزمایش است', voice='configured-voice-id', language='fa')
    assert result[0] == AUDIO and result[2:] == ('sarovi', 'elevenlabs/eleven-v4')
    assert seen == ['jarvis', 'sarovi']
    assert [r['status'] for r in rows] == ['failed', 'success']
    assert all(r['route'] == 'narration' and r['retry_count'] == 0 and r['latency_ms'] >= 0 for r in rows)
    assert 'secret-' not in json.dumps(rows) and 'ID3' not in json.dumps(rows)


@pytest.mark.parametrize('model', ['TTS_ELEVEN_MULTILINGUAL_V2', 'TTS_ELEVEN_FLASH_V2_5', 'TTS_ELEVEN_TURBO_V2_5', 'TTS_ELEVEN_V4'])
def test_persian_model_guard_before_any_post(monkeypatch, model):
    monkeypatch.setenv('NARRATION_TTS_ORDER', f'jarvis:{model}')
    monkeypatch.setattr(direct, '_audio_post', lambda *a, **k: pytest.fail('Unsafe model made a paid call'))
    assert direct.narration_pairs('این فارسی است') == []
    with pytest.raises(direct.DirectError, match='Persian'):
        direct.speech(providers()['jarvis'], model=model, text='این فارسی است', voice='v', language='fa')


def test_direct_plain_tts_no_relay_or_elevenlabs_key(monkeypatch, tmp_path):
    monkeypatch.delenv('ELEVENLABS_API_KEY', raising=False)
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'configured-id')
    monkeypatch.setenv('PERSIAN_ELEVENLABS_VOICE_ID', 'persian-id')
    seen = []
    monkeypatch.setattr(direct, '_audio_post', lambda p, path, **k: (seen.append((p['id'], path, k['body'])) or response(p['id'])))
    monkeypatch.setattr('httpx.get', lambda *a, **k: pytest.fail('No nonexistent relay catalog'))
    output = tmp_path / 'voice.mp3'
    tts._generate_elevenlabs('این آزمایش است', str(output), language='fa', with_timestamps=True)
    assert output.read_bytes() == AUDIO
    assert len(seen) == 1 and seen[0][2]['voice'] == 'persian-id'
    assert not Path(str(output) + '.words.json').exists()


def test_relay_still_selected_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv('ELEVENLABS_PROXY_URL', 'https://relay.example')
    seen = []
    monkeypatch.setattr(tts, '_generate_elevenlabs_relay', lambda *a, **k: seen.append(k))
    monkeypatch.setattr(direct, 'narration', lambda *a, **k: pytest.fail('Relay bypass'))
    tts._generate_elevenlabs('text', str(tmp_path / 'a.mp3'), with_timestamps=True)
    assert seen == [{'language': '', 'context': '', 'with_timestamps': True}]


@pytest.mark.parametrize('wire', ['json', 'multipart'])
def test_stt_wire_contract_word_mapping_and_audit(monkeypatch, tmp_path, wire):
    monkeypatch.setenv('SAROVI_STT_FORMAT', wire)
    rows = []
    monkeypatch.setattr(gateway, '_audit', rows.append)
    audio = tmp_path / 'voice.mp3'; audio.write_bytes(AUDIO)
    def post(request):
        assert request.headers['Authorization'] == 'Bearer secret-sarovi'
        assert request.url.path == '/v1/audio/transcriptions'
        if wire == 'multipart':
            body = request.content.decode()
            for field in ('name="file"', 'verbose_json', 'timestamp_granularities[]', 'word', 'fa'):
                assert field in body
        else:
            body = json.loads(request.content)
            assert base64.b64decode(body['audioBase64']) == AUDIO
            assert body['response_format'] == 'verbose_json' and body['timestamp_granularities[]'] == 'word'
            assert body['language'] == 'fa'
        return httpx.Response(200, json={'words': WORDS, 'language': 'fa', 'duration': 1.0})
    original = httpx.Client
    monkeypatch.setattr(direct.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(post), **kw))
    result = direct.transcription(providers()['sarovi'], audio, model='openai/whisper-large-v3', language='fa-IR')
    assert result['words'] == WORDS
    assert rows[0]['route'] == 'transcription' and rows[0]['status'] == 'success'
    assert rows[0]['provider'] == 'sarovi' and rows[0]['http_status'] == 200
    assert 'سلام' not in json.dumps(rows, ensure_ascii=False)


@pytest.mark.parametrize('payload', [{'text': 'سلام'}, {'segments': [{'text': 'سلام', 'start': 0, 'end': 1}]},
    {'words': []}, {'words': [{'word': 'سلام', 'start': float('nan'), 'end': 1}]},
    {'words': [{'word': 'سلام', 'start': 2, 'end': 1}]}, {'words': ['bad']}])
def test_stt_requires_real_word_timestamps(monkeypatch, tmp_path, payload):
    audio = tmp_path / 'a.mp3'; audio.write_bytes(AUDIO)
    monkeypatch.setattr(direct, '_audio_post', lambda *a, **k: httpx.Response(200, json=payload) if 'nan' not in str(payload).lower() else None)
    if 'nan' in str(payload).lower():
        with pytest.raises(direct.DirectError): direct.timed_words(payload)
    else:
        with pytest.raises(direct.DirectError, match='word timestamps'):
            direct.transcription(providers()['sarovi'], audio, model='openai/whisper-large-v3')


def test_chain_relay_sarovi_local_and_cache(monkeypatch, tmp_path):
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture')
    calls = []
    monkeypatch.setenv('ELEVENLABS_PROXY_URL', 'https://relay.example')
    def own(*a, **k):
        calls.append('relay'); raise RuntimeError('secret-in-error')
    def sarovi(*a, **k):
        calls.append('sarovi'); return {'words': []}, None
    def local(video, root, digest, *args):
        calls.append('whisper')
        value = {'file_hash': digest, 'engine': 'whisper', 'requested_language': 'fa', 'cache_key': 'key',
                 'words': [{'w': 'سلام', 'start': 0, 'end': 1, 'prob': .99}], 'sentences': []}
        (root / 'transcript.json').write_text(json.dumps(value)); return value
    monkeypatch.setattr(stt, 'transcribe_elevenlabs', own)
    monkeypatch.setattr(stt, 'transcribe_sarovi', sarovi)
    monkeypatch.setattr(transcribe, '_transcribe_whisper', local)
    root = tmp_path / 'job'
    result = transcribe.transcribe(video, root, language='fa', engine='elevenlabs')
    transcribe.transcribe(video, root, language='fa', engine='elevenlabs')
    assert calls == ['relay', 'sarovi', 'whisper'] and result['engine'] == 'whisper'
    assert [a['status'] for a in json.loads((root / 'asr_attempts.json').read_text())] == ['failed', 'failed', 'success']
    assert json.loads((root / 'asr_cost.json').read_text())['engine'] == 'whisper'
    assert 'secret-in-error' not in (root / 'transcript.json').read_text()


def test_sarovi_success_skips_local_and_is_cached(monkeypatch, tmp_path):
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture')
    calls = []
    def extract(v, root):
        audio = root / 'extracted.mp3'; audio.write_bytes(AUDIO); return audio
    monkeypatch.setattr(stt, '_extract_audio', extract)
    monkeypatch.setattr(direct, '_audio_post', lambda *a, **k: (calls.append('sarovi') or httpx.Response(200, json={'words': WORDS, 'duration': 1, 'language': 'fa'})))
    monkeypatch.setattr(stt, 'transcribe_elevenlabs', lambda *a, **k: pytest.fail('No relay configured'))
    monkeypatch.setattr(transcribe, '_transcribe_whisper', lambda *a, **k: pytest.fail('No fallback after success'))
    root = tmp_path / 'job'
    for _ in range(2):
        result = transcribe.transcribe(video, root, language='fa')
    assert result['engine'] == 'sarovi_whisper' and result['words'][0]['w'] == 'سلام'
    assert result['model_id'] == 'openai/whisper-large-v3' and calls == ['sarovi']
    assert json.loads((root / 'asr_cost.json').read_text())['cost_usd'] is None
    assert not (root / 'extracted.mp3').exists()


def test_plain_audio_alignment_uses_new_stt_chain(monkeypatch, tmp_path):
    from engine import narration_alignment as alignment
    audio = tmp_path / 'voice.mp3'; audio.write_bytes(AUDIO)
    calls = []
    def run(*a, **k):
        calls.append(k); return {'engine': 'sarovi_whisper', 'words': [{'w': 'سلام', 'start': 0, 'end': .8}]}
    monkeypatch.setattr(transcribe, 'transcribe', run)
    for _ in range(2):
        words, source = alignment.resolve(audio, 'سلام', 1, tmp_path)
    assert len(calls) == 1 and source == 'sarovi_whisper_stt' and words[0]['w'] == 'سلام'


def test_no_secret_in_errors_logs_or_audit(monkeypatch, tmp_path, caplog):
    rows = []
    monkeypatch.setattr(gateway, '_audit', rows.append)
    def post(request):
        return httpx.Response(500, text='secret-jarvis secret-sarovi raw-audio-base64')
    original = httpx.Client
    monkeypatch.setattr(direct.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(post), **kw))
    with pytest.raises(direct.DirectError) as error:
        direct.narration('این آزمایش است', voice='id', language='fa')
    audio = tmp_path / 'a.mp3'; audio.write_bytes(AUDIO)
    with pytest.raises(direct.DirectError):
        direct.transcription(providers()['sarovi'], audio, model='openai/whisper-large-v3')
    evidence = str(error.value) + caplog.text + json.dumps(rows)
    assert 'secret-jarvis' not in evidence and 'secret-sarovi' not in evidence
    assert 'raw-audio-base64' not in evidence


@pytest.mark.parametrize('mime,size', [('application/json', 2048), ('audio/mpeg', 0), ('audio/mpeg', 1023)])
def test_audio_type_and_size_validation(monkeypatch, mime, size):
    monkeypatch.setattr(direct, '_audio_post', lambda *a, **k: httpx.Response(200, content=b'x' * size, headers={'content-type': mime}))
    with pytest.raises(direct.DirectError, match='type or size'):
        direct.speech(providers()['jarvis'], model='TTS_ELEVEN_V3', text='text', voice='id')


def test_disabled_sarovi_and_explicit_local_do_not_call_hosted(monkeypatch, tmp_path):
    video = tmp_path / 'input.mp4'; video.write_bytes(b'fixture')
    monkeypatch.setenv('SAROVI_STT_ENABLED', 'false')
    monkeypatch.setattr(stt, 'transcribe_sarovi', lambda *a, **k: pytest.fail('Disabled Sarovi'))
    calls = []
    def local(video, root, digest, *args):
        calls.append('local')
        value = {'engine': 'whisper', 'words': [{'w': 'سلام', 'start': 0, 'end': 1, 'prob': 1}], 'sentences': []}
        (root / 'transcript.json').write_text(json.dumps(value)); return value
    monkeypatch.setattr(transcribe, '_transcribe_whisper', local)
    transcribe.transcribe(video, tmp_path / 'disabled', language='fa')
    monkeypatch.setenv('SAROVI_STT_ENABLED', 'true')
    transcribe.transcribe(video, tmp_path / 'explicit', language='fa', engine='whisper')
    assert calls == ['local', 'local']


def test_relay_each_timestamp_fallback_post_is_audited(monkeypatch, tmp_path):
    monkeypatch.setenv('ELEVENLABS_PROXY_URL', 'https://relay.example')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'secret-relay')
    monkeypatch.setattr(speech_policy, 'eleven_cast', lambda *a, **k: ('id', 'eleven_v3'))
    rows, calls = [], []
    monkeypatch.setattr(gateway, '_audit', rows.append)
    def post(url, **kwargs):
        calls.append(url)
        return httpx.Response(404 if len(calls) == 1 else 200, content=AUDIO, request=httpx.Request('POST', url))
    monkeypatch.setattr('httpx.post', post)
    tts._generate_elevenlabs('text', str(tmp_path / 'a.mp3'), voice_id='id', with_timestamps=True)
    assert [r['status'] for r in rows] == ['failed', 'success']
    assert [r['http_status'] for r in rows] == [404, 200]
    assert all(r['actual_model'] == 'eleven_v3' for r in rows)

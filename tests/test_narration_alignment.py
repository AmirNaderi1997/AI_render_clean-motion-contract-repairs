"""Offline provider contracts, script fidelity, timeline boundaries and publication hold."""
import base64
import json
from types import SimpleNamespace as NS

import pytest

from engine import narration_alignment as alignment
from engine.hyperframes import product_reel
from test_motion_contract_repairs import job_gate, config


WORDS = [{'w': 'اين', 'start': .4, 'end': .6}, {'w': 'محصول', 'start': .9, 'end': 1.3},
         {'w': '۱۲', 'start': 1.5, 'end': 1.8}, {'w': 'انتخاب', 'start': 2., 'end': 2.3},
         {'w': 'شماست', 'start': 2.6, 'end': 2.9}]
TEXT = 'این محصول ۱۲ انتخاب شماست'


@pytest.fixture
def reel(tmp_path):
    (tmp_path/'image.png').write_bytes(b'image')
    (tmp_path/'voice.mp3').write_bytes(b'voice')
    return {'scenes': [{'asset': 'image.png', 'narration': 'voice.mp3', 'narration_text': TEXT,
                        'frames': 90, 'title': '۱۲ انتخاب', 'kind': 'photo'}]}


def test_map_keeps_script_words_and_real_silences():
    mapped = alignment.map_script(TEXT, WORDS, 3)
    assert [w['w'] for w in mapped] == TEXT.split()
    assert [(w['start'], w['end']) for w in mapped] == [(w['start'], w['end']) for w in WORDS]
    # Repeated words keep their occurrence, not the first string match.
    assert alignment.map_script('بله بله', [{'w':'بله','start':0,'end':.2},
        {'w':'بله','start':1,'end':1.2}],2)[1]['start'] == 1


@pytest.mark.parametrize('bad', ['missing', 'overlap', 'nan', 'beyond', 'drift', 'number', 'no_words'])
def test_unsafe_alignment_is_estimated(tmp_path, monkeypatch, reel, bad):
    words = [dict(w) for w in WORDS]
    if bad == 'missing': words.pop(2)
    if bad == 'overlap': words[1]['start'] = .5
    if bad == 'nan': words[0]['start'] = float('nan')
    if bad == 'beyond': words[-1]['end'] = 4
    if bad == 'drift': words[2]['w'] = 'سیزده'
    if bad == 'number': words[2]['w'] = '۱۳'
    if bad == 'no_words': words = []
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs', lambda *a,**k: ({'words':words},0))
    prepared, report = alignment.prepare(reel, tmp_path)
    assert report['caption_timing'] == 'estimated'
    assert prepared['scenes'][0]['caption_words'] == []


def test_hash_cache_reused_across_names_and_script_remapped(tmp_path, monkeypatch, reel):
    calls = []
    def transcribe(audio, directory, **kwargs):
        calls.append(kwargs['file_digest'])
        return {'words': WORDS}, .001
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs', transcribe)
    first, report = alignment.prepare(reel, tmp_path)
    (tmp_path/'renamed.mp3').write_bytes(b'voice')
    reel['scenes'][0]['narration'] = 'renamed.mp3'
    reel['scenes'][0]['narration_text'] = TEXT.replace('محصول', 'محصول،')
    second, _ = alignment.prepare(reel, tmp_path)
    assert len(calls) == 1 and report['caption_timing'] == 'aligned'
    assert second['scenes'][0]['caption_words'][1]['w'] == 'محصول،'
    (tmp_path/'renamed.mp3').write_bytes(b'changed audio')
    alignment.prepare(reel, tmp_path)
    assert len(calls) == 2


def test_tts_sidecar_is_preferred_and_bound_to_audio(tmp_path, monkeypatch, reel):
    audio = tmp_path/'voice.mp3'
    alignment.sidecar(audio).write_text(json.dumps({'version':1,'audio_sha256':alignment.audio_hash(audio),
        'source':'elevenlabs_tts','words':WORDS}))
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs', lambda *a,**k: pytest.fail('paid STT'))
    prepared, report = alignment.prepare(reel,tmp_path)
    assert report['scenes'][0]['source'] == 'elevenlabs_tts'
    assert prepared['scenes'][0]['caption_words'][0]['w'] == 'این'
    audio.write_bytes(b'replaced audio')
    # The old sidecar is never used for different audio bytes.
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs',lambda *a,**k:({'words':WORDS},0))
    _, report = alignment.prepare(reel,tmp_path)
    assert report['scenes'][0]['source'] == 'elevenlabs_stt'


def test_provider_with_timestamps_audio_and_character_sidecar(tmp_path, monkeypatch):
    from brain import tts, lm_gateway
    monkeypatch.setattr(lm_gateway, 'configured', lambda:False)
    monkeypatch.setenv('ELEVENLABS_API_KEY','test')
    monkeypatch.setenv('ELEVENLABS_PROXY_URL','https://relay.example')
    monkeypatch.setattr('brain.speech_policy.eleven_cast',lambda *a,**k:('voice123','model'))
    requests = []
    def post(url, **kwargs):
        requests.append((url,kwargs))
        return NS(raise_for_status=lambda:None,json=lambda:{'audio_base64':base64.b64encode(b'audio').decode(),
          'alignment':{'characters':list('دو کار'),'character_start_times_seconds':[0,.1,.2,.3,.4,.5],
                       'character_end_times_seconds':[.1,.2,.3,.4,.5,.6]}})
    monkeypatch.setattr('httpx.post',post)
    audio=tmp_path/'n.mp3'
    tts._generate_elevenlabs('دو کار',str(audio),with_timestamps=True)
    assert requests[0][0].endswith('/voice123/with-timestamps')
    assert audio.read_bytes()==b'audio'
    data=json.loads(alignment.sidecar(audio).read_text())
    assert data['audio_sha256']==alignment.audio_hash(audio)
    assert data['words']==[{'w':'دو','start':0,'end':.2},{'w':'کار','start':.3,'end':.6}]


def test_generated_timeline_uses_measured_page_and_highlight_boundaries(tmp_path,monkeypatch,reel):
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs',lambda *a,**k:({'words':WORDS},0))
    gsap=tmp_path/'gsap.js';gsap.write_text('local')
    monkeypatch.setattr('engine.hyperframes.assets.ensure_gsap',lambda:gsap)
    reel['scenes'] *= 2
    page=product_reel.build_project(tmp_path/'page',reel,job_dir=tmp_path).read_text()
    assert 'tl.set("#s0c0",{opacity:1},0.4)' in page
    assert 'tl.set("#s0c1",{opacity:1},2.6)' in page
    assert 'tl.set("#s1c0",{opacity:1},3.4)' in page
    assert 'tl.set("#s0c0w1",{opacity:1,color:"#d9b36c"},0.9)' in page
    assert 'tl.set("#s0c0w1",{color:"#ffffff"},1.3)' in page
    assert '>این</span>' in page and '>اين</span>' not in page


@pytest.mark.parametrize('reason',['missing','failed','mismatch'])
def test_estimated_alignment_holds_app_candidate(job_gate,monkeypatch,reason):
    jobs,job,data = job_gate
    scene=data['generation_meta']['remotion']['scenes'][0]
    scene.update(narration_text='این محصول',frames=90)
    if reason!='missing':
        (job.dir/'voice.mp3').write_bytes(b'voice');scene['narration']='voice.mp3'
    calls=[]
    def transcribe(*a,**k):
        calls.append(1)
        if reason=='failed':raise RuntimeError('provider failure')
        return {'words':[{'w':'غلط','start':0,'end':.5}]},0
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs',transcribe)
    jobs._run_job(job,False)
    assert job.render.status=='needs_review' and job.render.output is None
    assert not job.versions and (job.dir/'exports'/job.render.candidate_output).is_file()
    assert job.render.technical_qc['caption_timing']=='estimated'
    assert len(calls)==(0 if reason=='missing' else 1)


def test_engine_fallback_does_not_repeat_failed_alignment(job_gate,monkeypatch):
    jobs,job,data=job_gate
    (job.dir/'v.mp3').write_bytes(b'voice')
    data['generation_meta']['remotion']['scenes'][0].update(narration='v.mp3',narration_text=TEXT,frames=90)
    calls=[]
    def fail_alignment(*a,**k):calls.append(1);raise RuntimeError('failure')
    def fail_render(*a,**k):raise RuntimeError('browser')
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs',fail_alignment)
    monkeypatch.setattr(product_reel,'render',fail_render)
    jobs._run_job(job,False)
    assert len(calls)==1 and job.render.renderer=='remotion' and job.render.status=='needs_review'


def test_aligned_app_candidate_publishes_with_timing_evidence(job_gate,monkeypatch):
    jobs,job,data=job_gate
    (job.dir/'voice.mp3').write_bytes(b'voice')
    data['generation_meta']['remotion']['scenes'][0].update(narration='voice.mp3',narration_text=TEXT,frames=90)
    monkeypatch.setattr('brain.transcribe_elevenlabs.transcribe_elevenlabs',lambda *a,**k:({'words':WORDS},0))
    jobs._run_job(job,False)
    assert job.render.status=='done' and job.render.output and job.versions
    assert job.render.technical_qc['caption_timing']=='aligned'
    assert job.render.technical_qc['scenes'][0]['words'][1]['start']==.9

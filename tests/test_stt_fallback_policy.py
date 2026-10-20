import json
import pytest
from brain import lm_direct,transcribe


def test_stt_settings_survive_text_provider_save(monkeypatch,tmp_path):
    monkeypatch.setattr(lm_direct.settings,'JOBS_DIR',str(tmp_path))
    value=lm_direct.save_config(False,[],{'enabled':True,'model':'medium','improve_low_quality':False})
    assert value['stt']['model']=='medium'
    assert lm_direct.save_config(True,[])['stt']==value['stt']
    with pytest.raises(ValueError):lm_direct.save_config(True,[],{'model':'invented'})


def test_whisper_review_preserves_timing_and_runs_once(monkeypatch,tmp_path):
    import brain.correct
    raw={'file_hash':'file','cache_key':'key','engine':'whisper','language':'fa','duration':1,
         'words':[{'w':'کلمه','start':0,'end':1,'prob':.5}],'sentences':[{'text':'کلمه','start':0,'end':1}]}
    (tmp_path/'transcript.json').write_text(json.dumps(raw))
    calls=[]
    def correct(*args):
        calls.append(1)
        return [{'index':0,'old':'کلمه','new':'کلمهٔ','confidence':.95,'type':'replace'}],None
    monkeypatch.setattr(brain.correct,'auto_correct',correct)
    result=transcribe.improve_local_transcript(raw,tmp_path)
    transcribe.improve_local_transcript(raw,tmp_path)
    assert len(calls)==1 and result['words'][0]['w']=='کلمهٔ'
    assert result['words'][0]['start']==0 and result['words'][0]['end']==1


def test_good_or_empty_transcript_does_not_call_ai(monkeypatch,tmp_path):
    import brain.correct
    monkeypatch.setattr(brain.correct,'auto_correct',lambda *a:pytest.fail('No unnecessary AI'))
    for words in [[],[{'w':'clear','prob':.99}]]:
        raw={'words':words};assert transcribe.improve_local_transcript(raw,tmp_path)==raw


def test_stt_priority_own_jarvis_sarovi_and_no_paid_repeat(monkeypatch,tmp_path):
    import brain.transcribe_elevenlabs as providers
    monkeypatch.setattr(lm_direct.settings,'JOBS_DIR',str(tmp_path))
    video=tmp_path/'input.mp4';video.write_bytes(b'fixture')
    calls=[]
    def own(*a,**kw):calls.append('own_vercel');raise RuntimeError('unavailable')
    def gateway(*a,provider,**kw):
        calls.append(provider)
        if provider=='jarvis':raise RuntimeError('unavailable')
        return {'engine':'elevenlabs_sarovi','file_hash':transcribe.file_hash(video),'requested_language':'fa','cache_key':'chain',
                'words':[{'w':'سلام','start':0,'end':1,'prob':.99}],
                'sentences':[{'text':'سلام','start':0,'end':1}]},None
    monkeypatch.setattr(providers,'transcribe_elevenlabs',own)
    monkeypatch.setattr(providers,'transcribe_gateway',gateway)
    root=tmp_path/'job'
    assert transcribe.transcribe(video,root,language='fa',engine='elevenlabs')['engine']=='elevenlabs_sarovi'
    transcribe.transcribe(video,root,language='fa',engine='elevenlabs')
    assert calls==['own_vercel','jarvis','sarovi']


def test_local_whisper_runs_only_after_all_remote_slots(monkeypatch,tmp_path):
    import brain.transcribe_elevenlabs as providers
    monkeypatch.setattr(lm_direct.settings,'JOBS_DIR',str(tmp_path))
    video=tmp_path/'input.mp4';video.write_bytes(b'fixture');calls=[]
    def own(*a,**k):calls.append('own');raise RuntimeError('unavailable')
    def remote(*a,provider,**k):calls.append(provider);raise RuntimeError('unavailable')
    def local(video,root,digest,model,*args):
        calls.append('whisper')
        assert model=='small'
        value={'file_hash':digest,'cache_key':'local','requested_language':'fa','engine':'whisper',
               'words':[{'w':'سلام','start':0,'end':1,'prob':.99}],
               'sentences':[{'text':'سلام','start':0,'end':1}]}
        (root/'transcript.json').write_text(json.dumps(value));return value
    monkeypatch.setattr(providers,'transcribe_elevenlabs',own)
    monkeypatch.setattr(providers,'transcribe_gateway',remote)
    monkeypatch.setattr(transcribe,'_transcribe_whisper',local)
    monkeypatch.setenv('WHISPER_ENABLED','true')
    result=transcribe.transcribe(video,tmp_path/'job',language='fa',engine='elevenlabs')
    assert result['engine']=='whisper' and calls==['own','jarvis','sarovi','whisper']

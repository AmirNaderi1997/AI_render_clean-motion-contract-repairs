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

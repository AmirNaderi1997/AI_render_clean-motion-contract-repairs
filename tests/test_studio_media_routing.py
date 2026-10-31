import pytest
import base64
import io
from PIL import Image
from brain import lm_gateway as gateway, lm_adapters
from brain.media_provider import get_provider


def test_image_generation_stays_on_arvan_even_with_a_text_provider(monkeypatch):
    monkeypatch.setattr(gateway,'configured',lambda:True)
    monkeypatch.setattr(gateway,'complete',lambda *a,**k:pytest.fail('images are not routed through the text router'))
    assert get_provider('arvan_image').name=='arvan_image'


def test_media_payload_and_redaction():
    payload=lm_adapters.payload('image','exact-model','prompt',extra={'n':1,'size':'1024x1024'})
    assert payload=={'model':'exact-model','prompt':'prompt','n':1,'size':'1024x1024'}
    assert 'ABCDEF' not in gateway.safe({'b64_json':'ABCDEF'})


def test_tts_uses_the_elevenlabs_transport_even_with_a_text_provider(monkeypatch,tmp_path):
    from brain.tts import _generate_elevenlabs
    monkeypatch.setattr(gateway,'configured',lambda:True)
    monkeypatch.delenv('ELEVENLABS_API_KEY',raising=False)
    with pytest.raises(RuntimeError,match='ElevenLabs is not configured'):
        _generate_elevenlabs('hello',str(tmp_path/'sample.mp3'),voice_id='existing-voice')


def test_resume_reuses_owned_job_and_rejects_other_users(monkeypatch,tmp_path):
    import pytest
    from types import SimpleNamespace
    from app import studio_store, studio_orchestrator as o
    from brain import content_creator
    from app.studio_store import repo,run
    monkeypatch.setattr(studio_store,'DB_AVAILABLE',False)
    monkeypatch.setattr(studio_store,'ROOT',tmp_path)
    monkeypatch.setattr(studio_store,'FALLBACK',tmp_path/'studio.json')
    conversation=run(repo.create_conversation('owner'))
    project=run(repo.create_project(conversation['id'],'owner','motion','Existing',{'confirmed':True},'same-job'))
    job=SimpleNamespace(dir=tmp_path,render=SimpleNamespace(status='idle'))
    monkeypatch.setattr(o.jobstore,'get',lambda ref: job if ref=='same-job' else None)
    monkeypatch.setattr(o,'_provider',lambda:'lm_gateway')
    generation={'state':'failed'};calls=[]
    monkeypatch.setattr(content_creator,'get_storyboard_status',lambda _:generation)
    def approve(existing,provider_name,**kwargs):
        assert existing is job
        calls.append(provider_name);generation['state']='generating'
    monkeypatch.setattr(content_creator,'approve_and_generate',approve)
    with pytest.raises(KeyError): o.resume_project(project['id'],'different-user')
    with pytest.raises(ValueError): o.resume_project(project['id'],'owner')
    assert calls==[]
    assert o.resume_project(project['id'],'owner',retry_confirmed=True)['stage']=='generating assets'
    assert o.resume_project(project['id'],'owner')['status']=='running'
    assert calls==['lm_gateway']
    assert run(repo.get_project(project['id'],'owner'))['external_ref']=='same-job'

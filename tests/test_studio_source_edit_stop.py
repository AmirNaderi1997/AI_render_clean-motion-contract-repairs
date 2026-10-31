"""Source-edit routing, cross-process stop boundaries, and verbatim edit plans."""
from types import SimpleNamespace
import pytest
from app import studio_orchestrator as o, studio_store as s, studio_flags
from app.studio_store import repo, run
from app.agents import store
from app.studio_cancel import Stopped, checkpoint, engine_guard


@pytest.mark.parametrize('text', [
    'Add Persian captions and remove pauses from this video.',
    'Add subtitles to the uploaded video', 'Trim this video', 'Cut mistakes from this video',
    'Remove silences from this upload',
    'روی همین ویدیو زیرنویس فارسی بگذار و مکث‌ها را حذف کن',
    'کپشن اضافه کن', 'سکوت ها را حذف کن', 'اشتباهات را حذف کن', 'این ویدیو را برش بزن',
])
@pytest.mark.parametrize('person', [False, True])
def test_explicit_edits_precede_classifier_and_visual_heuristics(monkeypatch, text, person):
    monkeypatch.setattr('brain.lm_gateway.configured', lambda: pytest.fail('No classifier for explicit edits'))
    assert o._resolved_intent(text, [{'kind':'video', 'metadata':{'person_detected':person}}], None) == 'source_edit'
    assert o._intent(text, [{'kind':'video'}], None) == 'source_edit'


@pytest.mark.parametrize('text', ['Make something like this reference with Persian captions',
    'این ویدیو رفرنس است؛ به سبک آن یک ویدیوی جدید با زیرنویس بساز'])
def test_explicit_reference_still_reaches_reference_analysis(monkeypatch, text):
    monkeypatch.setattr('brain.lm_gateway.configured', lambda: pytest.fail('Explicit role needs no classifier'))
    assert o._resolved_intent(text, [{'kind':'video'}], None) == 'motion'
    seen=[]
    monkeypatch.setattr(o, '_analyze_reference', lambda *a: seen.append(a[-1]) or SimpleNamespace(usable=False))
    o._gather_sources('cid','u',text,[{'kind':'video','path':'upload.mp4'}],video_role='reference')
    assert seen == ['upload.mp4']


def seed(mode='lite'):
    cid=run(repo.create_conversation('u'))['id']
    msg=run(repo.add_message(cid,'u','user','زیرنویس اضافه کن',agent_mode=mode))
    record=run(store.create_run(cid,'u',msg['id'],mode,{'text':msg['content'],'attachment_ids':[]}))
    run(store.update(record['id'],'u',patch={'stop_generation':studio_flags.generation('u',cid)}))
    return cid,msg,record


@pytest.fixture(autouse=True)
def local(monkeypatch):
    monkeypatch.setattr(s,'DB_AVAILABLE',False)
    yield
    engine_guard.set(None)


def test_stop_inside_creative_call_prevents_next_stage_retry_and_paid_call(monkeypatch):
    from creative import llm
    from creative.schemas import ScriptDraft
    from app.studio_activity import observe_request
    cid,msg,record=seed()
    stages=[];calls=[]
    monkeypatch.setattr(llm,'configured',lambda:True)
    @observe_request
    def fake_call(system,user,route,*a,**kw):
        calls.append(route)
        o.request_stop(cid,'u')
        raise RuntimeError('upstream failure after Stop')
    monkeypatch.setattr('brain.llm.gateway_json',fake_call)
    def work(*args):
        for _ in range(4):
            try:llm.ask(ScriptDraft,'system','user',route='script_writer')
            except llm.CreativeUnavailable:pass
        stages.append('next stage')
    monkeypatch.setattr(o,'_process_message',work)
    o.process_message(cid,'u',msg['id'],'edit',[])
    assert calls == ['script_writer'] and not stages
    assert run(store.get_run(record['id'],'u'))['status']=='cancelled'
    # Query events through the actual local store.
    rows=run(repo.events(cid,'u'))
    stop=next(i for i,e in enumerate(rows) if e['type']=='message.stopped')
    assert not any(e['type']=='tool.started' for e in rows[stop+1:])


def test_queued_lite_work_does_not_adopt_generation_after_stop(monkeypatch):
    cid,msg,record=seed()
    o.request_stop(cid,'u')
    monkeypatch.setattr(o,'_process_message',lambda *a:pytest.fail('queued work restarted'))
    o.process_message(cid,'u',msg['id'],'edit',[])
    assert run(store.get_run(record['id'],'u'))['status']=='cancelled'


def test_provider_fallback_cannot_start_after_stop(monkeypatch):
    from brain import lm_direct as d
    cid,_,_=seed();o._generation.set((cid,'u',0));calls=[]
    monkeypatch.setattr(d,'route_pairs',lambda *a,**k:[({'id':'jarvis','format':'openai'},'one'),({'id':'sarovi','format':'openai'},'two')])
    def call(*a,**k):
        calls.append(1);o.request_stop(cid,'u');raise d.DirectError('temporary',503)
    monkeypatch.setattr(d,'call',call)
    with pytest.raises(Stopped):d.complete_routed([],candidates=[],tokens=10,temperature=0,timeout=10,extra=None,attempts=[])
    assert len(calls)==1


def test_medium_nested_stage_stops_and_run_is_cancelled(monkeypatch):
    from app.agents.medium import nodes
    from app.agents.medium.graph import execute
    cid,msg,record=seed('medium');stages=[]
    monkeypatch.setattr(nodes,'opening',lambda *a:None)
    def context(record):
        o.request_stop(cid,'u')
        from app.studio_activity import describe
        with describe('creative_script','must not start'):stages.append('bad')
        return {}
    monkeypatch.setattr(nodes,'context',context)
    execute(run(store.get_run(record['id'],'u')))
    assert not stages and run(store.get_run(record['id'],'u'))['status']=='cancelled'


def test_source_edit_preserves_words_has_no_creative_or_generated_media(monkeypatch,tmp_path):
    from app import talking_reel as t, studio_source_edit as e
    from engine.talking_styles import talking_1 as media
    transcript={'duration':5.,'sentences':[{'start':.5,'end':4.,'text':'سلام این یک آزمایش است'}],
      'words':[{'start':.5,'end':1.,'w':'سلام'},{'start':1.1,'end':1.4,'w':'این'},
               {'start':2.5,'end':2.7,'w':'یک'},{'start':2.8,'end':3.3,'w':'آزمایش'},{'start':3.4,'end':4.,'w':'است'}]}
    monkeypatch.setattr(t,'transcript_for',lambda *a:transcript)
    monkeypatch.setattr('creative.direct_talk',lambda *a,**k:pytest.fail('creative stage'))
    monkeypatch.setattr('brain.talking_reel.recommend_style',lambda *a:pytest.fail('style selection'))
    state=t.load(tmp_path);state['source_edit']=True;t.save(tmp_path,state)
    t._analyze(tmp_path,tmp_path/'source.mp4',style=None,request='زیرنویس فارسی اضافه کن و مکث ها را حذف کن')
    state=t.load(tmp_path);assert state['analysis_ready']
    assert state['decisions']['captions']["0"]==transcript['sentences'][0]['text']
    assert state['music'] is None and state['creative_plan'] is None and not state['render_settings']['outro_logo']['enabled']
    plan=e.plan(media,transcript,state['decisions'],state)
    assert 0 < plan.duration < 5 and plan.captions
    assert all(not shot.close and not shot.push for shot in plan.shots)
    assert not plan.notes and not plan.flashes


def test_stop_in_background_engine_is_seen_even_without_conversation_context(tmp_path):
    from app import talking_reel as t
    t.save(tmp_path,{**t.load(tmp_path),'status':'canceled'})
    t._install_cancel_guard(tmp_path)
    with pytest.raises(Stopped):checkpoint()


def test_source_transcription_uses_configured_local_model(monkeypatch, tmp_path):
    from app import talking_reel as t
    t.save(tmp_path, {**t.load(tmp_path), 'source_edit': True})
    calls=[]
    monkeypatch.setattr('brain.lm_direct.config', lambda: {'stt': {'model':'small'}})
    monkeypatch.setattr('brain.transcribe.transcribe', lambda *a, **kw: calls.append(kw) or {'words':[{'w':'سلام'}]})
    t.transcript_for(tmp_path,tmp_path/'input.mp4')
    assert calls == [{'language':'fa','engine':'whisper','model_size':'small'}]


def test_source_export_qc_never_starts_creative_review(monkeypatch,tmp_path):
    from app import talking_reel as t
    t.save(tmp_path,{**t.load(tmp_path),'source_edit':True})
    monkeypatch.setattr('engine.probe.probe',lambda _: {'format':{'duration':'3'}})
    monkeypatch.setattr('engine.technical_qc.inspect_talking_export',lambda *a,**k: {'passed':True})
    monkeypatch.setattr('creative.review.review_export',lambda *a,**k:pytest.fail('creative review'))
    t._review_creative_output(tmp_path,tmp_path/'output.mp4')
    assert t.load(tmp_path)['technical_qc']=={'passed':True}


def test_stop_cancels_project_owned_by_another_worker(monkeypatch,tmp_path):
    from app import talking_reel as t
    cid,msg,record=seed()
    job=SimpleNamespace(id='worker-job',dir=tmp_path)
    state=t.load(tmp_path);state.update(status='running',stage='transcribing');t.save(tmp_path,state)
    monkeypatch.setattr(o.jobstore,'get',lambda _:job)
    project=run(repo.create_project(cid,'u','talking','Source',{},job.id))
    run(repo.update_project(project['id'],'u',status='running'))
    assert str(tmp_path) not in t._cancel_events  # API process has no worker event.
    result=o.request_stop(cid,'u')
    assert result['stopped']==['message','project']
    assert t.load(tmp_path)['status']=='canceled'
    assert run(repo.get_project(project['id'],'u'))['status']=='canceled'
    # A stale write by an in-flight operation cannot erase the durable flag.
    t.save(tmp_path,state)
    t._install_cancel_guard(tmp_path)
    with pytest.raises(Stopped):checkpoint()
    with pytest.raises(Stopped):t._checkpoint(tmp_path)

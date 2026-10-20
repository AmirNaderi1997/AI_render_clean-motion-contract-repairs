import asyncio
import json
from types import SimpleNamespace
from brain.motion_messages import MessageReader


def test_message_cursor_and_public_text_only(monkeypatch):
    reader=MessageReader('private-test-key');reader.initialized=True
    args=[]
    def rpc(method,params):
        assert method=='tools/call' and params['name']=='list_chat_messages'
        args.append(params['arguments'])
        return {'structuredContent':{'messages':[
            {'id':'user','role':'user','content':'not agent narration','sequence_num':1},
            {'id':'agent','role':'assistant','content':'<think>private reasoning</think>Animating the chart. private-test-key','sequence_num':2,'created_at':'2026-10-20T10:00:00Z'}],
            'has_more':False,'next_after_sequence':2}}
    monkeypatch.setattr(reader,'rpc',rpc)
    state={};reader.pull('owned-remote',state);reader.pull('owned-remote',state)
    assert len(state['messages'])==1
    assert state['message_cursor']==1 and args[1]['after_sequence']==1
    assert 'private reasoning' not in state['messages'][0]['text']
    assert 'private-test-key' not in state['messages'][0]['text']


def test_motion_activity_persists_once_after_refresh(monkeypatch,tmp_path):
    from app import studio_store as store
    from app import studio_orchestrator as orchestration
    monkeypatch.setattr(store,'DB_AVAILABLE',False)
    monkeypatch.setattr(store,'ROOT',tmp_path/'studio')
    monkeypatch.setattr(store,'FALLBACK',tmp_path/'studio.json')
    folder=tmp_path/'generated'/'motion_so';folder.mkdir(parents=True)
    (folder/('a'*24+'.json')).write_text(json.dumps({'job_id':'remote-job','status':'ready','messages':[
        {'id':'m1','revision':'v1','text':'Animating a diagram','timestamp':'now'}]}))
    async def scenario():
        conversation=await store.repo.create_conversation('owner')
        project=await store.repo.create_project(conversation['id'],'owner','motion','Test',{},'job')
        await orchestration._sync_motion_messages(conversation['id'],project,SimpleNamespace(dir=tmp_path),'owner')
        await orchestration._sync_motion_messages(conversation['id'],project,SimpleNamespace(dir=tmp_path),'owner')
        events=await store.repo.events(conversation['id'],'owner')
        assert [e['type'] for e in events]==['tool.started','tool.progress','tool.completed']
        # A lost local seen-cache still cannot duplicate persisted source IDs.
        project['state']['motion_event_ids']=[]
        await orchestration._sync_motion_messages(conversation['id'],project,SimpleNamespace(dir=tmp_path),'owner')
        assert len(await store.repo.events(conversation['id'],'owner'))==3
    asyncio.run(scenario())

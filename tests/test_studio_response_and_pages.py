import asyncio
from pathlib import Path
import pytest
from PIL import Image

from app import studio_orchestrator as o, studio_url as urls


def test_model_response_streams_before_persistence_and_uses_context(monkeypatch):
    from brain import lm_gateway as g
    events=[];saved=[]
    monkeypatch.setattr(g,'configured',lambda:True)
    def stream(route,messages,**kwargs):
        assert route=='conversation_response'
        assert messages[-2]['content']=='موشن بساز'
        assert messages[-1]['content']=='https://example.com/course'
        assert kwargs['tokens']==450
        yield 'لینک '
        assert events[-1][0]=='assistant.response.delta' and not saved
        yield 'دوره را بررسی می‌کنم.'
    monkeypatch.setattr(g,'stream_chat',stream)
    monkeypatch.setattr(o,'_emit',lambda cid,kind,**data:events.append((kind,data)))
    async def add(*args):saved.append(args[3]);return {'id':3}
    monkeypatch.setattr(o.repo,'add_message',add)
    assert o._stream_response('c','u',2,{'messages':[{'role':'user','content':'موشن بساز'},{'role':'user','content':'https://example.com/course'}]},[])
    assert saved==['لینک دوره را بررسی می‌کنم.']
    assert events[-1][0]=='assistant.response.completed'


def test_stream_failure_never_invents_a_canned_response(monkeypatch):
    from brain import lm_gateway as g
    monkeypatch.setattr(g,'configured',lambda:True)
    monkeypatch.setattr(g,'stream_chat',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('offline')))
    events=[]
    monkeypatch.setattr(o,'_emit',lambda cid,kind,**data:events.append((kind,data)))
    monkeypatch.setattr(o.repo,'add_message',lambda *a:pytest.fail('no fake response'))
    assert not o._stream_response('c','u',1,{'messages':[]},[])
    assert events[-1][0]=='assistant.response.failed' and events[-1][1]['text']==''


def test_spa_reader_uses_actual_dom_and_preserves_screenshots_not_as_assets(monkeypatch,tmp_path):
    from app import public_page_browser
    monkeypatch.setattr(urls,'_fetch',lambda url,**kw:(b'<title>Generic academy</title><div id="root"></div>',url,'text/html'))
    monkeypatch.setattr(public_page_browser,'render_page',lambda *a:{'title':'Actual course','content':'Actual course syllabus and specific teaching material. '*4,
        'images':[],'screenshots':[{'file':str(tmp_path/'shot.jpg'),'scroll_y':0}]})
    page=urls.inspect_page('https://example.com/course',tmp_path)
    assert page['title']=='Actual course'
    assert 'Actual course syllabus' in ' '.join(page['content'])
    assert page['screenshots'] and page['images']==[]


def test_screenshot_fallback_publishes_images_before_vision_failure(monkeypatch,tmp_path):
    from brain import llm
    shot=tmp_path/'shot.jpg';Image.new('RGB',(320,4001),'white').save(shot)
    async def create(*a,**k):return {'id':'shot-id'}
    monkeypatch.setattr(o.repo,'create_attachment',create)
    messages=[]
    monkeypatch.setattr(o,'_assistant',lambda *a:messages.append(a))
    monkeypatch.setattr(llm,'chat_vision',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('vision unavailable')))
    page={'url':'https://example.com','content':[],'screenshots':[{'file':str(shot)}]}
    with pytest.raises(RuntimeError):o._page_screenshots('c','u',page)
    assert messages[0][-1]==['shot-id']


def test_vision_reads_only_screenshots_when_dom_is_empty(monkeypatch,tmp_path):
    from brain import llm
    shot=tmp_path/'shot.jpg';Image.new('RGB',(320,4001),'white').save(shot)
    async def create(*a,**k):return {'id':'shot-id'}
    monkeypatch.setattr(o.repo,'create_attachment',create)
    monkeypatch.setattr(o,'_assistant',lambda *a:None)
    monkeypatch.setattr(llm,'chat_vision',lambda *a,**k:({'readable':True,'title':'Visible course','content':['Visible actual course details']},None))
    page={'url':'https://example.com','content':[],'screenshots':[{'file':str(shot)}],'images':[]}
    o._page_screenshots('c','u',page)
    assert page['extraction']=='screenshot_vision' and page['images']==[]
    tiles=sorted(tmp_path.glob('shot-read-*.jpg'),key=lambda p:int(p.stem.split('-')[-1]))
    assert [Image.open(p).height for p in tiles]==[1600,1600,801]

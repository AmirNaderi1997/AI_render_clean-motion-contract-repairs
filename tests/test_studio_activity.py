from app import studio_activity as activity
from brain import lm_gateway as gateway


def test_activity_is_scoped_and_preserves_result(monkeypatch):
    events = []
    monkeypatch.setattr(activity, 'report', lambda cid, kind, **data: events.append((cid,kind,data)))
    @activity.observe_request
    def request(route, **kwargs):
        return 'result'
    assert request('creative_director') == 'result'
    assert events == []
    token = gateway.conversation_context.set('owned-conversation')
    try:
        with activity.describe('creative_concepts', 'Exploring concepts'):
            assert request('creative_director') == 'result'
        assert request('creative_director', probe=True) == 'result'
    finally:
        gateway.conversation_context.reset(token)
    assert [e[1] for e in events] == ['tool.started','tool.completed']
    assert all(e[0]=='owned-conversation' for e in events)
    assert events[0][2]['activity_id'] == events[1][2]['activity_id']
    assert events[0][2]['thinking'] is True
    assert events[1][2]['thinking'] is False
    assert activity.description.get() is None


def test_smart_title_uses_existing_classification_call(monkeypatch):
    from app.studio_orchestrator import _resolved_intent
    from brain import llm
    monkeypatch.setattr(gateway, 'configured', lambda: True)
    calls=[]
    def classify(*args):
        calls.append(args)
        return {'intent':'motion','title':'تبلیغ ساعت هوشمند مشکی'}, None
    monkeypatch.setattr(llm,'gateway_json',classify)
    titles=[]
    assert _resolved_intent('برای ساعت هوشمند تبلیغ بساز',[],None,on_title=titles.append)=='motion'
    assert titles==['تبلیغ ساعت هوشمند مشکی']
    assert len(calls)==1
    assert calls[0][2]=='intent_classification'

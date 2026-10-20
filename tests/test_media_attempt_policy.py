import pytest
from brain.media_policy import response_timeout
from brain import lm_gateway as g


def test_missing_gateway_guard_fails_closed():
    from brain.media_policy import require_gateway_safety
    from types import SimpleNamespace
    client=SimpleNamespace(get=lambda *a,**k: SimpleNamespace(
        raise_for_status=lambda:None,json=lambda:{'version':0}))
    with pytest.raises(RuntimeError,match='no media request was submitted'):
        require_gateway_safety(client,'https://example.invalid/policy',{})


def test_minimum_and_heavy_response_budgets():
    assert response_timeout('image',5)==150
    assert response_timeout('speech',90)==200
    assert response_timeout('video',90)==300
    assert response_timeout('image',150,{'size':'2048x2048'})>=600
    assert response_timeout('speech',200,{'input':'x'*12000})>200
    assert response_timeout('video',300,{'duration':60})>=720
    assert response_timeout('image',900)==900


@pytest.mark.parametrize('status',[429,500,502,503,504])
def test_paid_image_never_retries_or_switches_models(monkeypatch,status):
    cfg={'enabled':True,'endpoint':'image','models':['first','second'],'automatic_fallback':True,
         'timeout':150,'max_retries':2,'max_tokens':4096,'temperature':None}
    monkeypatch.setattr(g,'defaults',lambda:{'image':cfg})
    monkeypatch.setattr(g,'gateway_settings',lambda:{'enabled':True})
    monkeypatch.setattr(g.store,'records',lambda _: {k:{'enabled':True,'verified':['image']} for k in cfg['models']})
    monkeypatch.setattr(g,'_audit',lambda _:None)
    monkeypatch.setattr(g,'_record',lambda *a,**kw:{})
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body['model']);raise g.GatewayError('simulated rejection',status,True)
    monkeypatch.setattr(g,'_wire',wire)
    with pytest.raises(g.GatewayError): g.complete('image','mock prompt')
    assert calls==['first']


def test_failed_media_requires_confirmation_before_provider_access(monkeypatch,tmp_path):
    import json
    from types import SimpleNamespace
    from brain import content_creator as c
    (tmp_path/'generation_status.json').write_text(json.dumps({'state':'failed'}))
    monkeypatch.setattr(c,'get_provider',lambda _:pytest.fail('must not access provider without confirmation'))
    with pytest.raises(ValueError): c.approve_and_generate(SimpleNamespace(dir=tmp_path),'lm_gateway')

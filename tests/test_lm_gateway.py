from types import SimpleNamespace
import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import lm_store as store
from app.config import settings
from app.routers import lm_admin
from brain import lm_gateway as g, lm_adapters as a, lm_direct as d

FIRST, SECOND = "custom:Exact/Case:1#jarvis-all-models", "custom:Other/2#sarovi-all-models"


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setenv("DIRECT_JARVIS_API_KEY", "private-test-credential")
    monkeypatch.setenv("DIRECT_SAROVI_API_KEY", "private-second-credential")
    cfg=g.defaults()["editing_agent"]
    cfg.update(models=[FIRST,SECOND],max_retries=0)
    store.save("routes",{"editing_agent":cfg})
    return cfg


def provider_calls(monkeypatch, answer):
    calls=[]
    def call(provider,messages,*,model,**kwargs):
        calls.append((provider["id"],model))
        return answer(len(calls),provider,model)
    monkeypatch.setattr(d,"call",call)
    return calls


def test_fallback_and_audit(monkeypatch,catalog):
    def answer(n,provider,model):
        if n==1: raise d.DirectError("HTTP 429: rate limit",429)
        return {"model":"Actual/Case","choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":3,"completion_tokens":2}}
    calls=provider_calls(monkeypatch,answer)
    token=g.job_context.set("job-123")
    try: data,record=g.complete("editing_agent",[{"role":"user","content":"hello"}])
    finally:g.job_context.reset(token)
    assert calls==[("jarvis","Exact/Case:1"),("sarovi","Other/2")]
    assert record["job_id"]=="job-123" and record["actual_model"]=="Actual/Case"
    assert record["provider"]=="sarovi" and record["routed_via"]=="direct:sarovi"
    assert record["cost"] is None and record["input_tokens"]==3
    assert len(record["fallback_history"])==2
    assert store.logs()["total"]==1


def test_invalid_json_skips_model_without_same_model_retry(monkeypatch,catalog):
    catalog.update(max_retries=2);store.save('routes',{'editing_agent':catalog})
    calls=provider_calls(monkeypatch,lambda n,p,m:{'choices':[{'message':{'content':'not JSON' if n==1 else '{"ok":true}'}}]})
    _,record=g.complete('editing_agent',[],validate_response=json.loads)
    assert calls==[('jarvis','Exact/Case:1'),('sarovi','Other/2')]
    assert record['fallback_count']==1


def test_disabled_vercel_never_runs(monkeypatch,catalog):
    catalog.update(models=["custom:vendor/model#vercel-all-models",SECOND]);store.save("routes",{"editing_agent":catalog})
    calls=provider_calls(monkeypatch,lambda n,p,m:{"choices":[{"message":{"content":"ok"}}]})
    g.complete("editing_agent",[])
    assert calls==[("sarovi","Other/2")]


def test_scoped_model_does_not_inherit_catalog_capabilities():
    assert g.capabilities({"scope_registered":True,"declared":["vision"],"verified":["chat"]})=={"chat"}


@pytest.mark.parametrize("status",[401,403])
def test_a_rejected_key_skips_the_rest_of_that_provider(monkeypatch,catalog,status):
    catalog.update(models=[FIRST,"custom:Another#jarvis-all-models",SECOND]);store.save("routes",{"editing_agent":catalog})
    def answer(n,provider,model):
        if provider["id"]=="jarvis": raise d.DirectError(f"HTTP {status}: no",status)
        return {"choices":[{"message":{"content":"ok"}}]}
    calls=provider_calls(monkeypatch,answer)
    g.complete("editing_agent",[])
    assert calls==[("jarvis","Exact/Case:1"),("sarovi","Other/2")]


def test_every_pair_failing_is_logged_once_with_the_last_reason(monkeypatch,catalog):
    def answer(n,provider,model): raise d.DirectError("HTTP 400: invalid",400)
    calls=provider_calls(monkeypatch,answer)
    with pytest.raises(g.GatewayError,match="HTTP 400"):g.complete("editing_agent",[])
    assert calls[:2]==[("jarvis","Exact/Case:1"),("sarovi","Other/2")]
    assert store.logs()["total"]==1 and store.logs()["items"][0]["status"]=="failed"


def test_without_automatic_fallback_only_the_first_model_runs(monkeypatch,catalog):
    catalog.update(automatic_fallback=False);store.save("routes",{"editing_agent":catalog})
    def answer(n,provider,model): raise d.DirectError("timeout",504)
    calls=provider_calls(monkeypatch,answer)
    with pytest.raises(g.GatewayError):g.complete("editing_agent",[])
    assert calls==[("jarvis","Exact/Case:1")]


def test_route_changes_apply_without_restart(monkeypatch,catalog):
    calls=provider_calls(monkeypatch,lambda n,p,m:{"choices":[{"message":{"content":"ok"}}]})
    g.complete("editing_agent",[])
    catalog["models"]=[SECOND];store.save("routes",{"editing_agent":catalog})
    g.complete("editing_agent",[])
    assert calls==[("jarvis","Exact/Case:1"),("sarovi","Other/2")]


def test_media_endpoints_are_not_routed(monkeypatch,catalog):
    provider_calls(monkeypatch,lambda *a:pytest.fail("must not call provider"))
    with pytest.raises(g.GatewayError,match="no direct provider"):g.complete("editing_agent",[],endpoint="image")


def test_adapters_keep_protocols_separate():
    messages=[{"role":"system","content":"rules"},{"role":"user","content":"hi"}]
    assert a.payload("responses","Case/Id",messages)["input"]==messages
    assert a.payload("messages","Case/Id",messages)["system"]=="rules"
    assert a.payload("embeddings","bge-m3",["hello"])["input"]==["hello"]
    assert a.text("responses",{"output":[{"content":[{"type":"output_text","text":"ok"}]}]})=="ok"
    assert a.text("messages",{"content":[{"type":"text","text":"ok"}]})=="ok"


def test_redaction(catalog):
    text=g.safe('private-test-credential Bearer other-secret data:image/png;base64,AAAA')
    assert "private-test-credential" not in text and "other-secret" not in text and "AAAA" not in text


def test_log_filters_pagination(catalog):
    for index in range(4):
        store.log({"id":str(index),"timestamp":f"2026-10-20T00:00:0{index}","route":"editing_agent",
                   "requested_model":FIRST,"status":"failed" if index%2 else "success"})
    assert store.logs({"status":"failed"},size=1)["total"]==2
    assert store.logs({"status":"failed"},page=2,size=1)["items"][0]["id"]=="1"


def admin_client(is_admin):
    app=FastAPI()
    @app.middleware("http")
    async def user(request,call_next):
        request.state.user=SimpleNamespace(id="owner" if is_admin else "regular",email="person@example.com")
        return await call_next(request)
    app.include_router(lm_admin.access_router);app.include_router(lm_admin.router)
    return TestClient(app)


def test_admin_authorization_and_key_secrecy(monkeypatch,catalog):
    monkeypatch.setattr(settings,"AI_ADMIN_USER_IDS","owner")
    assert admin_client(False).get("/admin/ai/models").status_code==403
    client=admin_client(True)
    response=client.get("/admin/ai/settings")
    assert response.status_code==200 and response.json()["configured"]
    assert "private-test-credential" not in response.text
    assert "private-test-credential" not in client.get("/admin/ai/direct").text
    assert client.get("/admin/ai/models").status_code==200


def test_stream_does_not_switch_after_first_token(monkeypatch,catalog):
    calls=[]
    def stream_call(provider,messages,*,model,**kwargs):
        calls.append((provider["id"],model))
        yield "first"
        raise d.DirectError("stream ended before completion",502)
    monkeypatch.setattr(d,"stream_call",stream_call)
    stream=g.stream_chat("editing_agent",[])
    assert next(stream)=="first"
    with pytest.raises(g.GatewayError):next(stream)
    assert calls==[("jarvis","Exact/Case:1")]
    assert store.logs()["items"][0]["status"]=="failed"


def test_sync_registers_task_models_without_any_network(monkeypatch,catalog):
    import httpx
    monkeypatch.setattr(httpx,"Client",lambda *a,**k:pytest.fail("no remote catalog exists"))
    result=g.sync_models()
    assert result["paths"]==[] and result["models"]>0
    rows=store.records("models").values()
    assert all(r["status"]=="Untested" and r["verified"]==[] for r in rows if r.get("scope_registered"))

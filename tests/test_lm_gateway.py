from types import SimpleNamespace
import json
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app import lm_store as store
from app.config import settings
from app.routers import lm_admin
from brain import lm_gateway as g, lm_adapters as a


@pytest.fixture
def catalog(monkeypatch):
    monkeypatch.setattr(settings,"LMAPI_API_KEY","private-test-credential")
    store.save("models",{mid:{"id":mid,"name":mid,"provider":"test","enabled":True,"available":True,
        "verified":["chat","vision","responses","messages","embeddings","streaming"],"declared":[],"status":"Healthy"} for mid in ("Exact/Case:1","Other/2")})
    cfg=g.defaults()["editing_agent"]
    cfg.update(models=["Exact/Case:1","Other/2"],max_retries=0)
    store.save("routes",{"editing_agent":cfg})
    return cfg


def test_fallback_and_audit(monkeypatch,catalog):
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body["model"])
        if len(calls)==1: raise g.GatewayError("rate limit",429,True)
        return {"model":"Actual/Case","choices":[{"message":{"content":"ok"}}],"usage":{"prompt_tokens":3,"completion_tokens":2}}, {"x-routed-via":"provider/Actual"},200
    monkeypatch.setattr(g,"_wire",wire)
    token=g.job_context.set("job-123")
    try: data,record=g.complete("editing_agent",[{"role":"user","content":"hello"}])
    finally:g.job_context.reset(token)
    assert calls==["Exact/Case:1","Other/2"]
    assert record["job_id"]=="job-123" and record["actual_model"]=="Actual/Case"
    assert record["cost"] is None and record["input_tokens"]==3
    assert len(record["fallback_history"])==2
    assert store.logs()["total"]==1


def test_a_model_missing_from_the_upstream_catalog_is_skipped_not_fatal(monkeypatch,catalog):
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body["model"])
        if len(calls)==1: raise g.GatewayError("LM API HTTP 404: model_not_found: Model is not in the catalog",404,False)
        return {"model":"Actual/Other","choices":[{"message":{"content":"ok"}}]},{},200
    monkeypatch.setattr(g,"_wire",wire)
    data,record=g.complete("editing_agent",[{"role":"user","content":"hello"}])
    assert calls==["Exact/Case:1","Other/2"] and record["actual_model"]=="Actual/Other"
    other=[]
    def refuse(endpoint,body,timeout):
        other.append(body["model"]); raise g.GatewayError("LM API HTTP 400: bad request",400,False)
    monkeypatch.setattr(g,"_wire",refuse)
    with pytest.raises(g.GatewayError):
        g.complete("editing_agent",[{"role":"user","content":"hello"}])
    assert other==["Exact/Case:1"]                                  # any other client error still stops the chain


def test_invalid_json_skips_model_without_same_model_retry(monkeypatch,catalog):
    catalog.update(max_retries=2);store.save('routes',{'editing_agent':catalog})
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body['model'])
        content='not JSON' if len(calls)==1 else '{"ok":true}'
        return {'choices':[{'message':{'content':content}}]}, {}, 200
    monkeypatch.setattr(g,'_wire',wire)
    _,record=g.complete('editing_agent',[],validate_response=json.loads)
    assert calls==['Exact/Case:1','Other/2']
    assert record['fallback_count']==1


def test_google_pin_rejects_different_provider_and_falls_back(monkeypatch,catalog):
    mid="google:gemini-3.5-flash"
    store.save("models",{mid:{"id":mid,"enabled":True,"available":True,"verified":["chat"],"scope_registered":True}})
    catalog.update(models=[mid,"Other/2"]);store.save("routes",{"editing_agent":catalog})
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body["model"])
        return {"choices":[{"message":{"content":"ok"}}]}, {"x-routed-via":"custom/gemini-3.5-flash"},200
    monkeypatch.setattr(g,"_wire",wire)
    _,record=g.complete("editing_agent",[])
    assert calls==[mid,"Other/2"]
    assert record["fallback_count"]==1


def test_disabled_vercel_never_runs(monkeypatch,catalog):
    mid="custom:vendor/model#vercel-all-models"
    store.save("models",{mid:{"id":mid,"enabled":True,"available":True,"verified":["chat"]}})
    catalog.update(models=[mid,"Other/2"]);store.save("routes",{"editing_agent":catalog})
    calls=[]
    def wire(endpoint,body,timeout):
        calls.append(body["model"]);return {"choices":[]},{},200
    monkeypatch.setattr(g,"_wire",wire)
    g.complete("editing_agent",[])
    assert calls==["Other/2"]


def test_scoped_model_does_not_inherit_catalog_capabilities():
    assert g.capabilities({"scope_registered":True,"declared":["vision"],"verified":["chat"]})=={"chat"}


@pytest.mark.parametrize("status",[400,401,403,422])
def test_no_fallback_on_invalid_request(monkeypatch,catalog,status):
    calls=[]
    def wire(*args):calls.append(1);raise g.GatewayError("invalid",status,False)
    monkeypatch.setattr(g,"_wire",wire)
    with pytest.raises(g.GatewayError):g.complete("editing_agent",[])
    assert len(calls)==1 and store.logs()["items"][0]["status"]=="failed"


def test_timeout_retries_are_bounded(monkeypatch,catalog):
    catalog.update(max_retries=1,models=["Exact/Case:1"]);store.save("routes",{"editing_agent":catalog})
    calls=[]
    monkeypatch.setattr(g.time,"sleep",lambda _:None)
    def wire(*args):calls.append(1);raise g.GatewayError("timeout",504,True)
    monkeypatch.setattr(g,"_wire",wire)
    with pytest.raises(g.GatewayError):g.complete("editing_agent",[])
    assert len(calls)==2


def test_route_changes_apply_without_restart(monkeypatch,catalog):
    calls=[]
    def wire(endpoint,body,timeout):calls.append(body["model"]);return {"choices":[]},{},200
    monkeypatch.setattr(g,"_wire",wire)
    g.complete("editing_agent",[])
    catalog["models"]=["Other/2"];store.save("routes",{"editing_agent":catalog})
    g.complete("editing_agent",[])
    assert calls==["Exact/Case:1","Other/2"]


def test_unverified_capability_is_not_executed(monkeypatch,catalog):
    def wire(*args):raise AssertionError("must not call provider")
    monkeypatch.setattr(g,"_wire",wire)
    with pytest.raises(g.GatewayError,match="verified"):g.complete("editing_agent",[],required={"image"})


def test_adapters_keep_protocols_separate():
    messages=[{"role":"system","content":"rules"},{"role":"user","content":"hi"}]
    assert a.payload("responses","Case/Id",messages)["input"]==messages
    assert a.payload("messages","Case/Id",messages)["system"]=="rules"
    assert a.payload("embeddings","bge-m3",["hello"])["input"]==["hello"]
    assert a.text("responses",{"output":[{"content":[{"type":"output_text","text":"ok"}]}]})=="ok"
    assert a.text("messages",{"content":[{"type":"text","text":"ok"}]})=="ok"


def test_actual_auto_model_comes_from_gateway_header(catalog):
    import time
    row=g._record("general_chat","messages","auto",time.monotonic(),[],
        {"model":"auto"},{"x-routed-via":"custom/Vendor%2FCase:Model"})
    assert row["actual_model"]=="Vendor/Case:Model" and row["provider"]=="custom"


def test_redaction(catalog):
    text=g.safe('private-test-credential Bearer other-secret data:image/png;base64,AAAA')
    assert "private-test-credential" not in text and "other-secret" not in text and "AAAA" not in text


def test_log_filters_pagination(catalog):
    for index in range(4):
        store.log({"id":str(index),"timestamp":f"2026-10-20T00:00:0{index}","route":"editing_agent",
                   "requested_model":"Exact/Case:1","status":"failed" if index%2 else "success"})
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
    assert response.status_code==200 and "private-test-credential" not in response.text
    assert client.get("/admin/ai/models").status_code==200
    assert client.put("/admin/ai/routes/embeddings",json={"models":["Exact/Case:1","Other/2"],"endpoint":"embeddings"}).status_code==422


def test_stream_does_not_switch_after_first_token(monkeypatch,catalog):
    catalog.update(streaming=True);store.save("routes",{"editing_agent":catalog})
    calls=[]
    class Stream:
        is_success=True;headers={}
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"first"}}]}'
            raise httpx.ReadTimeout("interrupted")
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def stream(self,*args,**kwargs):calls.append(kwargs["json"]["model"]);return Stream()
    monkeypatch.setattr(g,"_client",lambda _:Client())
    stream=g.stream_chat("editing_agent",[])
    assert next(stream)=="first"
    with pytest.raises(httpx.ReadTimeout):next(stream)
    assert calls==["Exact/Case:1"]
    assert store.logs()["items"][0]["status"]=="failed"


def test_catalog_preserves_case_and_no_name_guessing(monkeypatch,catalog):
    class Response:
        is_success=True
        def __init__(self,value):self.value=value
        def raise_for_status(self):pass
        def json(self):return self.value
    class Client:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def get(self,url,**kwargs):
            return Response({"data":[{"id":"Vendor/IMAGE-Vision:MiXeD","owned_by":"vendor"}]}) if url.endswith("models") else Response({"paths":{}})
    monkeypatch.setattr(g,"_client",lambda _:Client())
    g.sync_models(); row=store.records("models")["Vendor/IMAGE-Vision:MiXeD"]
    assert row["verified"]==[] and row["declared"]==[] and row["status"]=="Untested"

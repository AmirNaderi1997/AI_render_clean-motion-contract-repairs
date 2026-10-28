"""Actual content checks through shared Studio tools and LangGraph nodes."""
import asyncio

import pytest

from app import studio_store as studio, studio_tools
from app.agents import store
from app.agents.medium import nodes, tools
from app.agents.medium.state import EditingPlan


def call(coroutine):
    return asyncio.run(coroutine)


def seed(monkeypatch):
    monkeypatch.setattr(studio, "DB_AVAILABLE", False)
    conversation = call(studio.repo.create_conversation("alice"))
    message = call(studio.repo.add_message(conversation["id"], "alice", "user", "سناریو را بررسی کن", agent_mode="medium"))
    return call(store.create_run(conversation["id"], "alice", message["id"], "medium",
                                {"text": message["content"], "attachment_ids": []}))


def step():
    return {"tool": "instagram_content_check", "label": "بررسی زمان‌بندی سناریو",
            "arguments": {"operation": "beats", "language": "fa", "text": "می‌توانیم بهتر بنویسیم", "wpm": 120}}


def test_shared_tool_is_bounded_read_only_and_real():
    spec = studio_tools.TOOLS["instagram_content_check"]
    assert spec.idempotent and not spec.expensive
    result = studio_tools.execute(spec.name, step()["arguments"])
    assert result["result"]["total_words"] == 3
    assert result["result"]["total_seconds"] == 1.5
    assert result["result"]["beats"][0]["text"] == "می‌توانیم بهتر بنویسیم"


def test_medium_catalog_and_strict_plan_contract():
    plan = EditingPlan.model_validate({"summary": "بررسی متن", "steps": [step()]}).model_dump()
    entry = next(item for item in tools.catalog() if item["name"] == step()["tool"])
    assert not entry["requires_approval"]
    assert nodes.approval({}, {"plan": plan}) == {"approved": True}


def test_node_persists_result_emits_activity_and_does_not_repeat_completed_tool(monkeypatch):
    record = seed(monkeypatch)
    monkeypatch.setattr(nodes, "narrate_result", lambda *args: None)
    state = {"plan": {"steps": [step()]}, "index": 0, "rounds": 1, "results": []}
    result = nodes.tool(record, state)
    assert result["results"][0]["result"]["total_seconds"] == 1.5
    saved = call(store.get_run(record["id"], "alice"))
    assert saved["data"]["operations"]["1:0:instagram_content_check"]["status"] == "completed"
    events = call(studio.repo.events(record["conversation_id"], "alice"))
    assert any(item["type"] == "tool.completed" and item["data"].get("tool") == "instagram_content_check" for item in events)
    monkeypatch.setattr(tools, "execute", lambda *args: pytest.fail("completed check replayed"))
    assert nodes.tool(record, state) == result
    with pytest.raises(KeyError):
        call(store.get_run(record["id"], "bob"))


@pytest.mark.parametrize("extra", [{"path": "/etc/passwd"}, {"user_id": "bob"}, {"command": "whoami"}, {"wpm": float("nan")}])
def test_model_cannot_supply_paths_identity_shell_or_nonfinite_limits(extra):
    with pytest.raises(ValueError):
        studio_tools.execute("instagram_content_check", {**step()["arguments"], **extra})


def test_connected_app_adapter_uses_run_owner_not_model_identity(monkeypatch):
    from hermes.services import composio_read
    record = seed(monkeypatch)
    calls = []
    async def read(user, application, slug, arguments):
        calls.append((user, application, slug, arguments))
        return {"status": "completed", "data": {"profile": "mock"}}
    monkeypatch.setattr(composio_read, "execute", read)
    proposal = {"tool": "read_connected_app", "label": "خواندن اطلاعات مجاز",
                "arguments": {"application": "instagram", "tool": "INSTAGRAM_TEST_READ", "arguments": {"limit": 1}}}
    result = tools.execute(record, proposal)
    assert result["status"] == "completed"
    assert calls == [(record["user_key"], "instagram", "INSTAGRAM_TEST_READ", {"limit": 1})]
    assert "read_connected_app" in tools.READ_ONLY
    with pytest.raises(ValueError):
        tools.validate(record, {**proposal, "arguments": {**proposal["arguments"], "user_id": "bob"}})

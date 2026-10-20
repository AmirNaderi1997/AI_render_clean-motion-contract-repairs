import pytest
from brain.lm_tasks import TASKS, qualified_id


def test_preserves_execution_identity():
    assert qualified_id("jarvis", "CLAUDE_OPUS_5_5") == "custom:CLAUDE_OPUS_5_5#jarvis-all-models"
    assert qualified_id("sarovi", "openai/sora-2-pro") == "custom:openai/sora-2-pro#sarovi-all-models"
    assert qualified_id("google", "gemini-2.5-flash") == "google:gemini-2.5-flash"


@pytest.mark.parametrize("mid", ["", "x#other", "custom:x", "google:x", "x y"])
def test_rejects_injected_scope(mid):
    with pytest.raises(ValueError): qualified_id("jarvis", mid)


def test_policy_is_not_activation_evidence():
    assert len(TASKS) == 30
    for task in TASKS.values():
        assert "verified" not in task and "enabled" not in task
        assert len({p["id"] for p in task["preferences"]}) == len(task["preferences"])
    assert TASKS["transcription"]["preferences"] == []
    assert TASKS["embeddings"]["preferences"] == []
    assert all("vercel" not in p["id"] for t in TASKS.values() for p in t["preferences"])

"""A disabled account loses access at once, including access tokens issued before it was disabled."""
import asyncio
from types import SimpleNamespace

import pytest

from app import auth


def test_access_token_stops_working_when_the_account_is_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "USERS_FILE", tmp_path / "users.json")
    auth.register("disabled@example.com", "Test", "a-long-test-password")
    token = auth.login("disabled@example.com", "a-long-test-password")["access_token"]
    assert auth.get_current_user_from_token(token).email == "disabled@example.com"

    users = auth._load_users()
    for row in users.values():
        row["is_active"] = False
    auth._save_users(users)

    with pytest.raises(ValueError, match="ACCOUNT_DISABLED"):
        auth.get_current_user_from_token(token)


def test_database_lookup_rejects_a_disabled_account(monkeypatch):
    token = auth._create_access_token("7", "db@example.com", "Test")
    async def disabled(user_id):
        return SimpleNamespace(id=user_id, is_active=False)
    monkeypatch.setattr(auth, "db_get_user_by_id", disabled)
    with pytest.raises(ValueError, match="ACCOUNT_DISABLED"):
        asyncio.run(auth.db_get_current_user_from_token(token))

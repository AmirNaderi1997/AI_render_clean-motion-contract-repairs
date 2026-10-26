import json


def test_relay_uses_private_local_config_when_env_missing(monkeypatch, tmp_path):
    from app import page_relay
    monkeypatch.delenv('SOCIAL_RELAY_URL', raising=False)
    monkeypatch.delenv('SOCIAL_RELAY_SECRET', raising=False)
    monkeypatch.setattr(page_relay.settings, 'JOBS_DIR', str(tmp_path))
    folder=tmp_path/'ai_gateway';folder.mkdir()
    (folder/'page_relay.json').write_text(json.dumps({'url':'https://editorgpt-social-relay.vercel.app/api/index','secret':'x'*32}))
    assert page_relay.config()[1]=='x'*32


def test_relay_rejects_unapproved_endpoint(monkeypatch):
    from app import page_relay
    monkeypatch.setenv('SOCIAL_RELAY_URL','http://localhost:9000')
    monkeypatch.setenv('SOCIAL_RELAY_SECRET','x'*32)
    assert page_relay.config()==('', '')


def test_relay_target_does_not_weaken_literal_private_address_checks():
    import pytest
    from app.studio_url import _relay_public_url
    for url in ('http://127.0.0.1/x','http://[::1]/','http://192.168.1.2/','http://localhost/','http://service.internal/','https://u:p@example.com/'):
        with pytest.raises(ValueError): _relay_public_url(url)
    assert _relay_public_url('https://example.com/path')=='https://example.com/path'

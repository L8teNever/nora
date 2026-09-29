from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.claude import ClaudeFireError, resolve_credentials
from app.crypto import encrypt_secret
from app import config
from app.db import get_engine, init_db, reset_engine
from app.main import app
from app.models import Routine


def _client(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("NORA_DATABASE_URL", f"sqlite:///{tmp_path / 't.sqlite3'}")
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("NORA_ENCRYPTION_KEY", env.get("NORA_ENCRYPTION_KEY", key))
    monkeypatch.setenv("CLAUDE_ROUTINE_FIRE_URL", env.get("CLAUDE_ROUTINE_FIRE_URL", ""))
    monkeypatch.setenv("CLAUDE_ROUTINE_TOKEN", env.get("CLAUDE_ROUTINE_TOKEN", ""))
    config.get_settings.cache_clear()
    reset_engine()
    init_db()
    get_engine()
    return TestClient(app), key


def test_create_list_toggle_delete(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    r = client.post(
        "/routines",
        data={
            "name": "Nightly",
            "schedule_type": "cron",
            "cron_expr": "0 6 * * *",
            "interval_value": "60",
            "interval_unit": "minutes",
            "fire_url": "https://api.anthropic.com/v1/claude_code/routines/trig_test/fire",
            "token": "sk-ant-oat01-test",
            "fire_text": "hello",
            "enabled": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    listed = client.get("/api/routines").json()
    assert len(listed) == 1
    assert listed[0]["name"] == "Nightly"
    assert listed[0]["enabled"] is True
    rid = listed[0]["id"]
    client.post(f"/routines/{rid}/toggle", follow_redirects=False)
    listed = client.get("/api/routines").json()
    assert listed[0]["enabled"] is False
    client.post(f"/routines/{rid}/delete", follow_redirects=False)
    assert client.get("/api/routines").json() == []


def test_missing_creds_error(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    from app.db import SessionLocal

    db = SessionLocal()
    routine = Routine(
        name="x",
        enabled=True,
        schedule_type="cron",
        cron_expr="0 * * * *",
        interval_seconds=0,
        fire_url="",
        token_encrypted="",
    )
    db.add(routine)
    db.commit()
    try:
        resolve_credentials(routine)
        assert False, "expected missing creds"
    except ClaudeFireError as exc:
        assert "Missing Claude routine fire URL" in str(exc)


def test_encrypted_token_roundtrip(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    blob = encrypt_secret("sk-secret")
    assert blob and blob != "sk-secret"
    from app.crypto import decrypt_secret

    assert decrypt_secret(blob) == "sk-secret"

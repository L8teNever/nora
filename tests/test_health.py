from fastapi.testclient import TestClient

from app import config
from app.db import init_db, reset_engine
from app.main import app


def test_health(tmp_path, monkeypatch):
    monkeypatch.setenv("NORA_DATABASE_URL", f"sqlite:///{tmp_path / 't.sqlite3'}")
    monkeypatch.setenv("NORA_ENCRYPTION_KEY", "")
    config.get_settings.cache_clear()
    reset_engine()
    init_db()
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "nora"

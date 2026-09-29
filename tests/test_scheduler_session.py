from app import config
from app.db import init_db, reset_engine
from app.scheduler import reload_all, run_routine_job


def test_reload_all_uses_live_sessionlocal(tmp_path, monkeypatch):
    monkeypatch.setenv("NORA_DATABASE_URL", f"sqlite:///{tmp_path / 't.sqlite3'}")
    monkeypatch.setenv("NORA_ENCRYPTION_KEY", "")
    config.get_settings.cache_clear()
    reset_engine()
    init_db()
    reload_all()


def test_run_routine_job_uses_live_sessionlocal(tmp_path, monkeypatch):
    monkeypatch.setenv("NORA_DATABASE_URL", f"sqlite:///{tmp_path / 't.sqlite3'}")
    monkeypatch.setenv("NORA_ENCRYPTION_KEY", "")
    config.get_settings.cache_clear()
    reset_engine()
    init_db()
    run_routine_job(1)

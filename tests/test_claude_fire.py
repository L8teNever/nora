from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet

from app import config
from app.claude import fire_routine
from app.crypto import encrypt_secret
from app.db import init_db, reset_engine
from app.models import Routine


def test_fire_posts_expected_headers(tmp_path, monkeypatch):
    monkeypatch.setenv("NORA_DATABASE_URL", f"sqlite:///{tmp_path / 't.sqlite3'}")
    monkeypatch.setenv("NORA_ENCRYPTION_KEY", Fernet.generate_key().decode())
    config.get_settings.cache_clear()
    reset_engine()
    init_db()
    routine = Routine(
        name="x",
        enabled=True,
        schedule_type="cron",
        cron_expr="0 * * * *",
        fire_url="https://api.anthropic.com/v1/claude_code/routines/trig_x/fire",
        token_encrypted=encrypt_secret("sk-ant-oat01-abc"),
        fire_text="ping",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "type": "routine_fire",
        "claude_code_session_url": "https://claude.ai/code/session_x",
    }
    with patch("app.claude.httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_resp
        out = fire_routine(routine)
    post = client_cls.return_value.__enter__.return_value.post
    args, kwargs = post.call_args
    assert args[0].endswith("/fire")
    assert kwargs["headers"]["Authorization"] == "Bearer sk-ant-oat01-abc"
    assert kwargs["headers"]["anthropic-version"] == "2023-06-01"
    assert kwargs["json"] == {"text": "ping"}
    assert out["type"] == "routine_fire"

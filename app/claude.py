from __future__ import annotations

import logging

import httpx

from app.config import get_settings
from app.crypto import EncryptionError, decrypt_secret
from app.models import Routine

logger = logging.getLogger("nora.claude")

BETA_HEADER = "experimental-cc-routine-2026-04-01"


class ClaudeFireError(RuntimeError):
    pass


def resolve_credentials(routine: Routine) -> tuple[str, str]:
    settings = get_settings()
    url = (routine.fire_url or "").strip() or settings.claude_routine_fire_url.strip()
    token = ""
    if routine.token_encrypted:
        try:
            token = decrypt_secret(routine.token_encrypted)
        except EncryptionError as exc:
            raise ClaudeFireError(str(exc)) from exc
    if not token:
        token = settings.claude_routine_token.strip()
    if not url:
        raise ClaudeFireError(
            "Missing Claude routine fire URL. Set it on the job or CLAUDE_ROUTINE_FIRE_URL."
        )
    if not token:
        raise ClaudeFireError(
            "Missing Claude routine token. Set it on the job or CLAUDE_ROUTINE_TOKEN."
        )
    return url, token


def fire_routine(routine: Routine) -> dict:
    url, token = resolve_credentials(routine)
    settings = get_settings()
    headers = {
        "Authorization": f"Bearer {token}",
        "anthropic-version": settings.anthropic_version or "2023-06-01",
        "anthropic-beta": BETA_HEADER,
        "Content-Type": "application/json",
    }
    body: dict = {}
    if routine.fire_text:
        body["text"] = routine.fire_text

    logger.info("Firing Claude routine job id=%s name=%s url=%s", routine.id, routine.name, url)
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise ClaudeFireError(f"HTTP error calling Claude routine API: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text[:2000]
        raise ClaudeFireError(f"Claude API returned {response.status_code}: {detail}")

    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.claude import ClaudeFireError, fire_routine, resolve_credentials
from app.config import get_settings
from app.crypto import EncryptionError, encrypt_secret
from app.db import get_db, init_db
from app.models import Routine
from app.scheduler import remove_job, start_scheduler, upsert_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("nora")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    start_scheduler()
    yield


app = FastAPI(title="Nora", description="Claude Code routine scheduler UI", lifespan=lifespan)
BASE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def _validate_schedule(schedule_type: str, cron_expr: str, interval_seconds: int) -> None:
    if schedule_type not in ("cron", "interval"):
        raise HTTPException(400, "schedule_type must be cron or interval")
    if schedule_type == "cron" and not cron_expr.strip():
        raise HTTPException(400, "cron expression is required")
    if schedule_type == "cron":
        from apscheduler.triggers.cron import CronTrigger

        try:
            CronTrigger.from_crontab(cron_expr.strip())
        except Exception as exc:
            raise HTTPException(400, f"Invalid cron expression: {exc}") from exc
    if schedule_type == "interval" and int(interval_seconds or 0) < 60:
        raise HTTPException(400, "interval must be at least 60 seconds")


def _apply_token(routine: Routine, token: str) -> None:
    token = (token or "").strip()
    if not token:
        return
    try:
        routine.token_encrypted = encrypt_secret(token)
    except EncryptionError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "service": "nora",
        "has_default_fire_url": bool(settings.claude_routine_fire_url.strip()),
        "has_default_token": bool(settings.claude_routine_token.strip()),
        "has_encryption_key": bool(settings.nora_encryption_key.strip()),
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    routines = db.query(Routine).order_by(Routine.id.desc()).all()
    settings = get_settings()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "routines": routines,
            "has_defaults": bool(
                settings.claude_routine_fire_url.strip() and settings.claude_routine_token.strip()
            ),
            "has_encryption_key": bool(settings.nora_encryption_key.strip()),
        },
    )


@app.get("/routines/new", response_class=HTMLResponse)
def new_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "form.html",
        {"routine": None, "action": "/routines", "title": "New schedule"},
    )


@app.get("/routines/{routine_id}/edit", response_class=HTMLResponse)
def edit_form(routine_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    return templates.TemplateResponse(
        request,
        "form.html",
        {"routine": routine, "action": f"/routines/{routine.id}", "title": "Edit schedule"},
    )


def _form_to_fields(
    name: str,
    schedule_type: str,
    cron_expr: str,
    interval_value: str,
    interval_unit: str,
    fire_url: str,
    fire_text: str,
    enabled: str | None,
) -> dict:
    interval_seconds = 0
    if schedule_type == "interval":
        try:
            raw = int(interval_value or "0")
        except ValueError as exc:
            raise HTTPException(400, "interval must be an integer") from exc
        unit = interval_unit or "minutes"
        if unit == "hours":
            interval_seconds = raw * 3600
        else:
            interval_seconds = raw * 60
    _validate_schedule(schedule_type, cron_expr, interval_seconds)
    return {
        "name": name.strip() or "Untitled",
        "schedule_type": schedule_type,
        "cron_expr": cron_expr.strip(),
        "interval_seconds": interval_seconds,
        "fire_url": fire_url.strip(),
        "fire_text": fire_text.strip(),
        "enabled": enabled == "on",
    }


@app.post("/routines")
def create_routine(
    name: Annotated[str, Form()],
    schedule_type: Annotated[str, Form()],
    cron_expr: Annotated[str, Form()] = "",
    interval_value: Annotated[str, Form()] = "60",
    interval_unit: Annotated[str, Form()] = "minutes",
    fire_url: Annotated[str, Form()] = "",
    token: Annotated[str, Form()] = "",
    fire_text: Annotated[str, Form()] = "",
    enabled: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    fields = _form_to_fields(
        name, schedule_type, cron_expr, interval_value, interval_unit, fire_url, fire_text, enabled
    )
    routine = Routine(**fields)
    _apply_token(routine, token)
    db.add(routine)
    db.commit()
    db.refresh(routine)
    try:
        upsert_job(routine)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@app.post("/routines/{routine_id}")
def update_routine(
    routine_id: int,
    name: Annotated[str, Form()],
    schedule_type: Annotated[str, Form()],
    cron_expr: Annotated[str, Form()] = "",
    interval_value: Annotated[str, Form()] = "60",
    interval_unit: Annotated[str, Form()] = "minutes",
    fire_url: Annotated[str, Form()] = "",
    token: Annotated[str, Form()] = "",
    fire_text: Annotated[str, Form()] = "",
    enabled: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    fields = _form_to_fields(
        name, schedule_type, cron_expr, interval_value, interval_unit, fire_url, fire_text, enabled
    )
    for key, value in fields.items():
        setattr(routine, key, value)
    _apply_token(routine, token)
    db.commit()
    db.refresh(routine)
    try:
        upsert_job(routine)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return RedirectResponse("/", status_code=303)


@app.post("/routines/{routine_id}/toggle")
def toggle_routine(routine_id: int, db: Session = Depends(get_db)):
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    routine.enabled = not routine.enabled
    db.commit()
    db.refresh(routine)
    upsert_job(routine)
    return RedirectResponse("/", status_code=303)


@app.post("/routines/{routine_id}/delete")
def delete_routine(routine_id: int, db: Session = Depends(get_db)):
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    remove_job(routine.id)
    db.delete(routine)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.post("/routines/{routine_id}/run")
def run_now(routine_id: int, db: Session = Depends(get_db)):
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    try:
        payload = fire_routine(routine)
        routine.last_run_status = "ok"
        routine.last_run_error = ""
        routine.last_session_url = str(payload.get("claude_code_session_url") or "")
    except ClaudeFireError as exc:
        routine.last_run_status = "error"
        routine.last_run_error = str(exc)
    from datetime import datetime, timezone

    routine.last_run_at = datetime.now(timezone.utc)
    db.commit()
    return RedirectResponse("/", status_code=303)


@app.get("/api/routines")
def api_list(db: Session = Depends(get_db)):
    routines = db.query(Routine).order_by(Routine.id.desc()).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "enabled": r.enabled,
            "schedule": r.schedule_label(),
            "fire_url_set": bool(r.fire_url),
            "token_set": bool(r.token_encrypted),
            "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
            "last_run_status": r.last_run_status,
            "last_run_error": r.last_run_error,
            "last_session_url": r.last_session_url,
        }
        for r in routines
    ]


@app.post("/api/routines/{routine_id}/run")
def api_run(routine_id: int, db: Session = Depends(get_db)):
    routine = db.get(Routine, routine_id)
    if routine is None:
        raise HTTPException(404, "Routine not found")
    try:
        resolve_credentials(routine)
        payload = fire_routine(routine)
        return JSONResponse(payload)
    except ClaudeFireError as exc:
        raise HTTPException(400, str(exc)) from exc

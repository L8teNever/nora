from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app import db as db_module
from app.claude import ClaudeFireError, fire_routine
from app.config import get_settings
from app.models import Routine

logger = logging.getLogger("nora.scheduler")

scheduler = AsyncIOScheduler()


def _job_id(routine_id: int) -> str:
    return f"routine-{routine_id}"


def run_routine_job(routine_id: int) -> None:
    db_module.get_engine()
    db: Session = db_module.SessionLocal()
    try:
        routine = db.get(Routine, routine_id)
        if routine is None or not routine.enabled:
            return
        try:
            payload = fire_routine(routine)
            routine.last_run_status = "ok"
            routine.last_run_error = ""
            routine.last_session_url = str(
                payload.get("claude_code_session_url") or payload.get("session_url") or ""
            )
        except ClaudeFireError as exc:
            logger.error("Routine %s failed: %s", routine_id, exc)
            routine.last_run_status = "error"
            routine.last_run_error = str(exc)
        routine.last_run_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _trigger_for(routine: Routine):
    tz = get_settings().nora_tz or "UTC"
    if routine.schedule_type == "cron":
        if not routine.cron_expr.strip():
            raise ValueError("cron expression is required")
        return CronTrigger.from_crontab(routine.cron_expr.strip(), timezone=tz)
    if routine.schedule_type == "interval":
        seconds = int(routine.interval_seconds or 0)
        if seconds < 60:
            raise ValueError("interval must be at least 60 seconds")
        return IntervalTrigger(seconds=seconds, timezone=tz)
    raise ValueError(f"Unknown schedule_type: {routine.schedule_type}")


def upsert_job(routine: Routine) -> None:
    jid = _job_id(routine.id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)
    if not routine.enabled:
        return
    trigger = _trigger_for(routine)
    scheduler.add_job(
        run_routine_job,
        trigger=trigger,
        id=jid,
        args=[routine.id],
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
    )


def remove_job(routine_id: int) -> None:
    jid = _job_id(routine_id)
    if scheduler.get_job(jid):
        scheduler.remove_job(jid)


def reload_all() -> None:
    db_module.get_engine()
    db = db_module.SessionLocal()
    try:
        for routine in db.query(Routine).all():
            try:
                upsert_job(routine)
            except Exception as exc:
                logger.error("Could not schedule routine %s: %s", routine.id, exc)
    finally:
        db.close()


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.configure(timezone=get_settings().nora_tz or "UTC")
        scheduler.start()
    reload_all()

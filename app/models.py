from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Routine(Base):
    __tablename__ = "routines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    schedule_type: Mapped[str] = mapped_column(String(20), nullable=False)  # cron | interval
    cron_expr: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fire_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    token_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    fire_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    last_run_error: Mapped[str] = mapped_column(Text, default="", nullable=False)
    last_session_url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    def schedule_label(self) -> str:
        if self.schedule_type == "cron":
            return f"cron {self.cron_expr}"
        seconds = self.interval_seconds or 0
        if seconds % 3600 == 0 and seconds >= 3600:
            hours = seconds // 3600
            return f"every {hours}h"
        if seconds % 60 == 0 and seconds >= 60:
            return f"every {seconds // 60}m"
        return f"every {seconds}s"

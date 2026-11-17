from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def local_today(tz: str = "Asia/Kolkata") -> date:
    return datetime.now(tz=ZoneInfo(tz)).date()


def start_of_local_day_utc(tz: str = "Asia/Kolkata") -> datetime:
    zone = ZoneInfo(tz)
    now = datetime.now(tz=zone)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)

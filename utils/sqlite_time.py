from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_sqlite_utc_timestamp(value: Any) -> datetime | None:
    """
    Parse a SQLite `CURRENT_TIMESTAMP`-style value as UTC.

    SQLite typically stores timestamps as `YYYY-MM-DD HH:MM:SS` text.
    Some drivers may return `datetime` objects depending on adapters.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


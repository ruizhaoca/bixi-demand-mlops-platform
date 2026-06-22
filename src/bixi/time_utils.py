"""Timezone helpers shared by the Streamlit deployments."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

MONTREAL_TIMEZONE = ZoneInfo("America/Toronto")


def montreal_today(now: dt.datetime | None = None) -> dt.date:
    """Return Montreal's calendar date, independent of the server timezone."""
    if now is None:
        now = dt.datetime.now(dt.timezone.utc)
    elif now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(MONTREAL_TIMEZONE).date()

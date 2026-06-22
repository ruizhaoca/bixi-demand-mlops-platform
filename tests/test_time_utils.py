"""Timezone boundary checks for the Streamlit forecast window."""

import datetime as dt

import pytest

from bixi.time_utils import montreal_today


def test_montreal_today_does_not_follow_utc_midnight():
    utc_after_midnight = dt.datetime(2026, 6, 22, 1, 0, tzinfo=dt.timezone.utc)
    assert montreal_today(utc_after_midnight) == dt.date(2026, 6, 21)


def test_montreal_today_advances_at_local_midnight():
    utc_after_montreal_midnight = dt.datetime(
        2026, 6, 22, 4, 1, tzinfo=dt.timezone.utc
    )
    assert montreal_today(utc_after_montreal_midnight) == dt.date(2026, 6, 22)


def test_montreal_today_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        montreal_today(dt.datetime(2026, 6, 22, 1, 0))

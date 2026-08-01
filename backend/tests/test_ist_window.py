"""Tests for backend/services/ist_window.py (SS-029 design §6.1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from services.ist_window import (
    IST,
    ist_day_key,
    ist_month_key,
    ist_today,
    seconds_until_next_ist_midnight,
    seconds_until_next_ist_month_start,
)
from services.rate_limiter import _seconds_until_next_ist_midnight


def test_ist_day_key_uses_asia_kolkata_not_utc() -> None:
    # 2026-08-31T19:00:00Z = 2026-09-01 00:30 IST
    utc_time = datetime(2026, 8, 31, 19, 0, 0, tzinfo=UTC)
    assert ist_day_key(utc_time) == "2026-09-01"
    assert ist_day_key(utc_time) != "2026-08-31"


def test_ist_today_matches_ist_day_key() -> None:
    utc_time = datetime(2026, 8, 31, 19, 0, 0, tzinfo=UTC)
    assert ist_today(utc_time).isoformat() == "2026-09-01"


def test_seconds_until_next_ist_midnight_is_exact_not_86400() -> None:
    # 23:30 IST -> 30 minutes to midnight.
    at_2330_ist = datetime(2026, 7, 30, 23, 30, 0, tzinfo=IST)
    assert seconds_until_next_ist_midnight(at_2330_ist) == 1800


def test_ist_midnight_boundary_is_1830_utc_not_0000_utc() -> None:
    """The literal "resets at 05:30 IST" bug the ticket names would fail
    this: IST midnight is 18:30 UTC of the PRIOR day, not 00:00 UTC."""
    just_before_ist_midnight = datetime(2026, 7, 30, 18, 29, 0, tzinfo=UTC)
    seconds = seconds_until_next_ist_midnight(just_before_ist_midnight)
    assert seconds == 60

    just_after_ist_midnight = datetime(2026, 7, 30, 18, 30, 1, tzinfo=UTC)
    seconds_after = seconds_until_next_ist_midnight(just_after_ist_midnight)
    # Just rolled over -- almost a full day left, not a few seconds.
    assert seconds_after > 86000


def test_seconds_until_next_ist_month_start_handles_31_30_and_february() -> None:
    # Jan 31 23:00 IST -> Feb 1 00:00 IST = 1 hour.
    jan_31 = datetime(2026, 1, 31, 23, 0, 0, tzinfo=IST)
    assert seconds_until_next_ist_month_start(jan_31) == 3600

    # Feb (28 days in 2026, not a leap year) 27 23:00 IST -> Mar 1 00:00 IST.
    feb_27 = datetime(2026, 2, 27, 23, 0, 0, tzinfo=IST)
    expected = int(
        (datetime(2026, 3, 1, 0, 0, 0, tzinfo=IST) - feb_27).total_seconds()
    )
    assert seconds_until_next_ist_month_start(feb_27) == expected

    # Apr (30 days) 29 23:00 IST -> May 1 00:00 IST.
    apr_29 = datetime(2026, 4, 29, 23, 0, 0, tzinfo=IST)
    expected_apr = int(
        (datetime(2026, 5, 1, 0, 0, 0, tzinfo=IST) - apr_29).total_seconds()
    )
    assert seconds_until_next_ist_month_start(apr_29) == expected_apr


def test_ist_month_rollover_across_year_boundary() -> None:
    dec_31 = datetime(2026, 12, 31, 23, 59, 0, tzinfo=IST)
    assert ist_month_key(dec_31 + timedelta(minutes=1, seconds=1)) == "2027-01"
    assert seconds_until_next_ist_month_start(dec_31) == 60


def test_rate_limiter_helper_delegates_unchanged() -> None:
    """Regression guard: services/rate_limiter.py's own
    _seconds_until_next_ist_midnight must still behave identically after
    delegating to services/ist_window.py (SS-029)."""
    at_2330_ist = datetime(2026, 7, 30, 23, 30, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    assert _seconds_until_next_ist_midnight(at_2330_ist) == 1800
    assert _seconds_until_next_ist_midnight(at_2330_ist) == seconds_until_next_ist_midnight(
        at_2330_ist
    )

"""Single home for IST (``Asia/Kolkata``) calendar day/month key derivation
and seconds-to-next-boundary math (SS-029 design §2.1).

Before this module, the "seconds until next IST midnight" logic lived only
in ``services/rate_limiter.py``'s private ``_seconds_until_next_ist_midnight``
-- SS-029 needed a second copy (daily budget key) plus a brand-new monthly
sibling, which would have made a *third* copy of the same reasoning. This
module is now the only place either lives; ``rate_limiter.py`` delegates to
it (see its own updated docstring) rather than duplicating it, and every new
key/TTL SS-029 needs is derived from here too.

Keys carry the IST calendar date/month, not UTC -- so key rotation *is* the
reset (TTL is only garbage collection), and a UTC-based implementation's
05:30-IST-reset bug is structurally impossible: the boundary is always
computed against ``Asia/Kolkata`` wall-clock time, never UTC.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


def ist_today(now: datetime | None = None) -> date:
    """Today's calendar date in IST wall-clock time -- what price-table
    resolution and ledger writes key off of, never UTC's ``date.today()``."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    return current.date()


def ist_day_key(now: datetime | None = None) -> str:
    """``YYYY-MM-DD`` in IST wall-clock time."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    return current.strftime("%Y-%m-%d")


def ist_month_key(now: datetime | None = None) -> str:
    """``YYYY-MM`` in IST wall-clock time."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    return current.strftime("%Y-%m")


def seconds_until_next_ist_midnight(now: datetime | None = None) -> int:
    """Exact seconds remaining until the next 00:00 IST (``Asia/Kolkata``),
    not a fixed 86400 -- combined with the IST-date-in-key convention, this
    is what makes "resets at IST midnight, not UTC" literally true rather
    than an approximate rolling window."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    next_midnight = (current + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((next_midnight - current).total_seconds()))


def seconds_until_next_ist_month_start(now: datetime | None = None) -> int:
    """Exact seconds remaining until the 1st of next IST calendar month at
    00:00. Handles 28/29/30/31-day months and December -> January rollover
    without any hardcoded day count."""
    current = now.astimezone(IST) if now else datetime.now(IST)
    if current.month == 12:
        next_month_start = current.replace(
            year=current.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    else:
        next_month_start = current.replace(
            month=current.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return max(1, int((next_month_start - current).total_seconds()))

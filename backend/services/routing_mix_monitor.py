"""Rolling routing-mix + provider-outage detector (SS-028 design §7).

Part of "done", not a follow-on -- the raw ticket's own framing: a router
that quietly sends everything to the expensive model throws no error, so
these two production assertions are the detection mechanism.

**Honest limitation (state in the worklog too):** in-process only. With >1
worker each process sees a fraction of traffic, so the expensive-share
signal is directionally right but not exact, and there is no deployed
multi-worker backend to verify against yet (``BL-037``). The durable,
queryable version of this signal is SS-029's ledger -- complementary, not a
dependency; this module must not depend on SS-029 to satisfy AC #6.

Sentry hygiene: real ``sentry_sdk`` calls must be no-ops under test.
``backend/tests/conftest.py`` already blanks ``SENTRY_DSN_BACKEND`` at
collection time -- but tests for THIS module assert on an injected
``notify`` callable, never by capturing real Sentry traffic (constructor
arg ``notify``, defaulting to the Sentry+logger implementation below).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable
from typing import Protocol

import sentry_sdk

logger = logging.getLogger(__name__)


class _DecisionLike(Protocol):
    # Read-only properties, not plain attributes -- ``RoutingDecision`` is a
    # frozen dataclass, and mypy treats a plain-attribute Protocol member as
    # requiring a SETTABLE field, which a frozen dataclass's fields are not.
    @property
    def provider(self) -> str: ...

    @property
    def cost_class(self) -> str: ...


def _default_notify(event: str, payload: dict[str, object]) -> None:
    # Every alert ALSO emits a plain logger.warning (design §7.3) so the
    # signal survives Sentry being unconfigured (SENTRY_DSN_BACKEND unset
    # locally / blanked in tests).
    sentry_sdk.capture_message(event, level="warning")
    logger.warning(event, extra=payload)


class RoutingMixMonitor:
    def __init__(
        self,
        *,
        alert_min_sample: int = 20,
        expensive_share_alert_threshold: float = 0.30,
        alert_cooldown_seconds: float = 3600.0,
        provider_outage_alert_seconds: float = 900.0,
        window_size: int = 1000,
        notify: Callable[[str, dict[str, object]], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._alert_min_sample = alert_min_sample
        self._expensive_share_alert_threshold = expensive_share_alert_threshold
        self._alert_cooldown_seconds = alert_cooldown_seconds
        self._provider_outage_alert_seconds = provider_outage_alert_seconds
        self._notify = notify or _default_notify
        self._clock = clock or time.monotonic

        # Rolling window of recent decisions' cost_class -- a single high-
        # stakes first call (sample size 1) must never page anyone
        # (alert_min_sample gate below).
        self._decisions: deque[str] = deque(maxlen=max(window_size, alert_min_sample))
        self._last_share_alert_at: float | None = None

        # Per-provider outage tracking: first_failure_at starts a streak;
        # any success clears it (a single success resets the streak).
        self._first_failure_at: dict[str, float] = {}
        self._last_outage_alert_at: dict[str, float] = {}

    def configure(
        self,
        *,
        alert_min_sample: int | None = None,
        expensive_share_alert_threshold: float | None = None,
        alert_cooldown_seconds: float | None = None,
        provider_outage_alert_seconds: float | None = None,
    ) -> None:
        """Live-applies a freshly-read ``ai_router_policy`` config value onto
        the SAME shared instance (mirrors ``ProviderQuotaTracker.set_ceilings``
        and ``GeminiRateLimiter.set_max_requests``) -- called once per
        request with the current snapshot's values so a config edit changes
        alerting behaviour with no redeploy. ``None`` leaves a field
        unchanged. The rolling decision window itself is untouched."""
        if alert_min_sample is not None:
            self._alert_min_sample = alert_min_sample
            if self._decisions.maxlen is not None and self._decisions.maxlen < alert_min_sample:
                self._decisions = deque(self._decisions, maxlen=alert_min_sample)
        if expensive_share_alert_threshold is not None:
            self._expensive_share_alert_threshold = expensive_share_alert_threshold
        if alert_cooldown_seconds is not None:
            self._alert_cooldown_seconds = alert_cooldown_seconds
        if provider_outage_alert_seconds is not None:
            self._provider_outage_alert_seconds = provider_outage_alert_seconds

    def record(self, decision: _DecisionLike, outcome: str) -> None:
        """Fed one call per ROUTER ATTEMPT (design §7's ``record(decision,
        outcome)``), not one per request -- a request with two failovers
        feeds this three times."""
        now = self._clock()
        self._decisions.append(decision.cost_class)
        self._check_expensive_share(now)

        provider = decision.provider
        if outcome == "success":
            self._first_failure_at.pop(provider, None)
        else:
            self._first_failure_at.setdefault(provider, now)
            self._check_outage(provider, now)

    def _check_expensive_share(self, now: float) -> None:
        total = len(self._decisions)
        if total < self._alert_min_sample:
            return
        high_stakes = sum(1 for cost_class in self._decisions if cost_class == "high_stakes")
        share = high_stakes / total
        if share <= self._expensive_share_alert_threshold:
            return
        if (
            self._last_share_alert_at is not None
            and (now - self._last_share_alert_at) < self._alert_cooldown_seconds
        ):
            return
        self._last_share_alert_at = now
        self._notify(
            "ai_routing_expensive_share_exceeded",
            {
                "share": share,
                "total": total,
                "high_stakes": high_stakes,
                "threshold": self._expensive_share_alert_threshold,
            },
        )

    def provider_is_down(self, provider: str, *, now: float | None = None) -> bool:
        """(SS-039) True iff ``provider``'s current failure streak (tracked
        by ``record()``, cleared on any success) has lasted
        ``>= self._provider_outage_alert_seconds`` -- reuses the EXACT same
        state/threshold that already drives the existing Sentry
        ``ai_routing_provider_outage`` alert (design SS-028 §7), so "down"
        here is literally what an operator is already paged for, not a new
        definition invented for this ticket. A freshly-constructed monitor
        (no ``record()`` calls yet) has an empty ``_first_failure_at``, so
        this returns ``False`` for every provider -- a cold-started process
        never spuriously resolves to E0."""
        first_failure_at = self._first_failure_at.get(provider)
        if first_failure_at is None:
            return False
        current_time = now if now is not None else self._clock()
        return (current_time - first_failure_at) >= self._provider_outage_alert_seconds

    def _check_outage(self, provider: str, now: float) -> None:
        first_failure_at = self._first_failure_at.get(provider)
        if first_failure_at is None:
            return
        if now - first_failure_at < self._provider_outage_alert_seconds:
            return
        last_alert_at = self._last_outage_alert_at.get(provider)
        if last_alert_at is not None and (now - last_alert_at) < self._alert_cooldown_seconds:
            return
        self._last_outage_alert_at[provider] = now
        self._notify(
            "ai_routing_provider_outage",
            {
                "provider": provider,
                "failing_since": first_failure_at,
                "duration_seconds": now - first_failure_at,
            },
        )

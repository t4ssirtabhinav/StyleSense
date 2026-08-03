"""Tests for backend/services/routing_mix_monitor.py (SS-028 design §11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from services.routing_mix_monitor import RoutingMixMonitor


@dataclass(frozen=True)
class _FakeDecision:
    provider: str
    cost_class: str


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _Notifications:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event: str, payload: dict) -> None:
        self.events.append((event, payload))


def _make_monitor(**kwargs: Any) -> tuple[RoutingMixMonitor, _Notifications, _FakeClock]:
    notify = _Notifications()
    clock = _FakeClock()
    monitor = RoutingMixMonitor(notify=notify, clock=clock, **kwargs)
    return monitor, notify, clock


def test_share_below_threshold_never_notifies() -> None:
    monitor, notify, _ = _make_monitor(alert_min_sample=5, expensive_share_alert_threshold=0.5)
    decision = _FakeDecision(provider="gemini", cost_class="everyday")
    for _ in range(20):
        monitor.record(decision, "success")

    assert notify.events == []


def test_share_above_threshold_with_enough_sample_fires_exactly_once() -> None:
    monitor, notify, _ = _make_monitor(alert_min_sample=10, expensive_share_alert_threshold=0.3)
    high_stakes = _FakeDecision(provider="claude", cost_class="high_stakes")
    everyday = _FakeDecision(provider="gemini", cost_class="everyday")

    for _ in range(4):
        monitor.record(high_stakes, "success")
    for _ in range(6):
        monitor.record(everyday, "success")

    share_alerts = [e for e in notify.events if e[0] == "ai_routing_expensive_share_exceeded"]
    assert len(share_alerts) == 1


def test_below_alert_min_sample_never_fires_regardless_of_share() -> None:
    monitor, notify, _ = _make_monitor(alert_min_sample=100, expensive_share_alert_threshold=0.1)
    high_stakes = _FakeDecision(provider="claude", cost_class="high_stakes")

    for _ in range(10):
        monitor.record(high_stakes, "success")

    assert notify.events == []


def test_cooldown_suppresses_second_alert_and_permits_one_after_it_expires() -> None:
    monitor, notify, clock = _make_monitor(
        alert_min_sample=2,
        expensive_share_alert_threshold=0.0,
        alert_cooldown_seconds=100.0,
    )
    decision = _FakeDecision(provider="claude", cost_class="high_stakes")

    monitor.record(decision, "success")
    monitor.record(decision, "success")
    first_count = len([e for e in notify.events if e[0] == "ai_routing_expensive_share_exceeded"])
    assert first_count == 1

    monitor.record(decision, "success")
    second_count = len([e for e in notify.events if e[0] == "ai_routing_expensive_share_exceeded"])
    assert second_count == 1  # suppressed by cooldown

    clock.advance(101.0)
    monitor.record(decision, "success")
    third_count = len([e for e in notify.events if e[0] == "ai_routing_expensive_share_exceeded"])
    assert third_count == 2


def test_provider_failing_continuously_past_outage_seconds_fires_once() -> None:
    monitor, notify, clock = _make_monitor(
        alert_min_sample=1000,  # keep the expensive-share detector silent
        provider_outage_alert_seconds=60.0,
    )
    decision = _FakeDecision(provider="gemini", cost_class="everyday")

    monitor.record(decision, "transient")
    clock.advance(30.0)
    monitor.record(decision, "transient")
    outage_alerts = [e for e in notify.events if e[0] == "ai_routing_provider_outage"]
    assert outage_alerts == []

    clock.advance(31.0)  # now 61s since the first failure
    monitor.record(decision, "transient")
    outage_alerts = [e for e in notify.events if e[0] == "ai_routing_provider_outage"]
    assert len(outage_alerts) == 1


def test_a_single_success_resets_the_outage_streak() -> None:
    monitor, notify, clock = _make_monitor(
        alert_min_sample=1000,
        provider_outage_alert_seconds=60.0,
    )
    decision = _FakeDecision(provider="gemini", cost_class="everyday")

    monitor.record(decision, "transient")
    clock.advance(70.0)
    monitor.record(decision, "success")  # resets the streak
    clock.advance(70.0)
    monitor.record(decision, "transient")  # a brand-new streak, only 0s old

    outage_alerts = [e for e in notify.events if e[0] == "ai_routing_provider_outage"]
    assert outage_alerts == []


def test_notifications_go_through_the_injected_notifier_never_real_sentry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sentry_sdk

    calls: list[str] = []
    monkeypatch.setattr(sentry_sdk, "capture_message", lambda *a, **k: calls.append("called"))

    monitor, notify, _ = _make_monitor(alert_min_sample=1, expensive_share_alert_threshold=0.0)
    monitor.record(_FakeDecision(provider="claude", cost_class="high_stakes"), "success")

    assert notify.events  # our injected notifier WAS called
    assert calls == []  # the real sentry_sdk path was never touched

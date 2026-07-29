"""Tests for backend/services/app_config.py (SS-026) -- design §7.1.

No real network/DB calls -- a fake ``IAppConfigRepository`` stands in for
``SupabaseAppConfigRepository`` throughout.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic import BaseModel

from adapters.interfaces import IAppConfigRepository
from services.app_config import (
    CACHE_TTL_SPEC,
    DEFAULT_CACHE_TTL_SECONDS,
    MAX_CACHE_TTL_SECONDS,
    MIN_CACHE_TTL_SECONDS,
    AppConfigService,
    AppConfigSnapshot,
    CacheTtlConfig,
    ConfigSpec,
    _clamp_ttl,
)
from services.app_config_specs import GEMINI_QUOTA_CEILING_SPEC
from services.gemini_rate_limiter import GeminiRateLimiter


class _WidgetConfig(BaseModel):
    enabled: bool = False


WIDGET_SPEC: ConfigSpec[_WidgetConfig] = ConfigSpec(
    key="widget_enabled", model=_WidgetConfig, default=_WidgetConfig()
)


class _AnotherConfig(BaseModel):
    label: str = "default-label"


ANOTHER_SPEC: ConfigSpec[_AnotherConfig] = ConfigSpec(
    key="another_key", model=_AnotherConfig, default=_AnotherConfig()
)


class _FakeRepository(IAppConfigRepository):
    def __init__(self, values: dict[str, Any] | None = None, *, raises: bool = False) -> None:
        self.values = values or {}
        self.raises = raises
        self.call_count = 0

    async def fetch_all(self) -> dict[str, Any]:
        self.call_count += 1
        if self.raises:
            raise RuntimeError("supabase unreachable")
        return self.values


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _patch_clock(monkeypatch: pytest.MonkeyPatch, clock: _FakeClock) -> None:
    import services.app_config as app_config_module

    monkeypatch.setattr(app_config_module.time, "monotonic", clock)


async def test_snapshot_cache_hit_calls_fetch_all_once_within_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    repo = _FakeRepository({"widget_enabled": {"enabled": True}})
    service = AppConfigService(repo, initial_ttl_seconds=60)

    await service.snapshot()
    clock.advance(10)
    await service.snapshot()

    assert repo.call_count == 1


async def test_snapshot_cache_miss_after_ttl_expiry_refetches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    repo = _FakeRepository({"widget_enabled": {"enabled": True}})
    service = AppConfigService(repo, initial_ttl_seconds=60)

    await service.snapshot()
    clock.advance(10)
    await service.snapshot()
    clock.advance(60)
    await service.snapshot()

    assert repo.call_count == 2


async def test_read_missing_key_returns_default_logs_info(caplog: pytest.LogCaptureFixture) -> None:
    repo = _FakeRepository({})
    service = AppConfigService(repo)
    snapshot = await service.snapshot()

    with caplog.at_level("INFO", logger="services.app_config"):
        result = service.read(snapshot, WIDGET_SPEC)

    assert result == WIDGET_SPEC.default
    assert any(
        r.levelname == "INFO" and "app_config_key_missing" in r.message for r in caplog.records
    )


async def test_read_malformed_value_returns_default_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    repo = _FakeRepository({"widget_enabled": {"enabled": "not-a-bool-and-not-coercible"}})
    service = AppConfigService(repo)
    snapshot = await service.snapshot()

    with caplog.at_level("ERROR", logger="services.app_config"):
        result = service.read(snapshot, WIDGET_SPEC)

    assert result == WIDGET_SPEC.default
    assert any(
        r.levelname == "ERROR" and "app_config_value_invalid" in r.message for r in caplog.records
    )


async def test_malformed_one_row_does_not_break_others() -> None:
    repo = _FakeRepository(
        {
            "widget_enabled": {"enabled": "not-a-bool-and-not-coercible"},
            "another_key": {"label": "real-value"},
        }
    )
    service = AppConfigService(repo)
    snapshot = await service.snapshot()

    assert service.read(snapshot, WIDGET_SPEC) == WIDGET_SPEC.default
    assert service.read(snapshot, ANOTHER_SPEC) == _AnotherConfig(label="real-value")


async def test_supabase_unreachable_first_call_returns_empty_stale_snapshot() -> None:
    repo = _FakeRepository(raises=True)
    service = AppConfigService(repo)

    snapshot = await service.snapshot()

    assert snapshot.stale is True
    assert snapshot.values == {}
    assert service.read(snapshot, WIDGET_SPEC) == WIDGET_SPEC.default


async def test_supabase_unreachable_subsequent_call_falls_back_to_last_good_marked_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    # Seed config_cache_ttl_seconds explicitly -- otherwise the
    # self-referential-TTL adoption (§3.5) would overwrite the constructor's
    # initial_ttl_seconds=5 with the coded default (60s) on the first
    # successful fetch, and a 10s clock advance would then be a cache hit,
    # not the expiry this test means to exercise.
    repo = _FakeRepository(
        {"widget_enabled": {"enabled": True}, "config_cache_ttl_seconds": {"seconds": 5}}
    )
    service = AppConfigService(repo, initial_ttl_seconds=5)

    good_snapshot = await service.snapshot()
    assert good_snapshot.stale is False

    repo.raises = True
    clock.advance(10)
    fallback_snapshot = await service.snapshot()

    assert fallback_snapshot.stale is True
    assert fallback_snapshot.values == good_snapshot.values
    assert service.read(fallback_snapshot, WIDGET_SPEC) == _WidgetConfig(enabled=True)


async def test_snapshot_never_raises_even_when_repository_raises() -> None:
    repo = _FakeRepository(raises=True)
    service = AppConfigService(repo)

    # Should not raise.
    snapshot = await service.snapshot()
    assert isinstance(snapshot, AppConfigSnapshot)


async def test_one_request_one_snapshot_read_never_triggers_a_hidden_refetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    repo = _FakeRepository({"widget_enabled": {"enabled": True}})
    service = AppConfigService(repo, initial_ttl_seconds=60)

    snapshot = await service.snapshot()
    # Mutate what the repository WOULD return next -- the held snapshot
    # must be unaffected since read() never re-fetches.
    repo.values = {"widget_enabled": {"enabled": False}}

    first_read = service.read(snapshot, WIDGET_SPEC)
    second_read = service.read(snapshot, WIDGET_SPEC)

    assert first_read == second_read == _WidgetConfig(enabled=True)
    assert repo.call_count == 1


@pytest.mark.parametrize(
    "raw_value",
    [
        MIN_CACHE_TTL_SECONDS - 1,
        MAX_CACHE_TTL_SECONDS + 1000,
        float("nan"),
        "not-a-number",
    ],
)
def test_clamp_ttl_never_propagates_a_bad_value_raw(raw_value: Any) -> None:
    result = _clamp_ttl(raw_value)
    assert MIN_CACHE_TTL_SECONDS <= result <= MAX_CACHE_TTL_SECONDS


def test_clamp_ttl_under_min_clamps_to_min() -> None:
    assert _clamp_ttl(MIN_CACHE_TTL_SECONDS - 1) == MIN_CACHE_TTL_SECONDS


def test_clamp_ttl_over_max_clamps_to_max() -> None:
    assert _clamp_ttl(MAX_CACHE_TTL_SECONDS + 1000) == MAX_CACHE_TTL_SECONDS


def test_clamp_ttl_nan_degrades_to_default() -> None:
    assert _clamp_ttl(float("nan")) == DEFAULT_CACHE_TTL_SECONDS


def test_clamp_ttl_non_numeric_string_degrades_to_default() -> None:
    assert _clamp_ttl("not-a-number") == DEFAULT_CACHE_TTL_SECONDS  # type: ignore[arg-type]


async def test_self_referential_ttl_adopts_freshly_read_value_not_constructor_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _FakeClock()
    _patch_clock(monkeypatch, clock)
    repo = _FakeRepository({CACHE_TTL_SPEC.key: {"seconds": 120}})
    service = AppConfigService(repo, initial_ttl_seconds=5)

    await service.snapshot()
    # If the service adopted the constructor's initial_ttl_seconds=5, a
    # second call after 10s would refetch. If it correctly adopted the
    # freshly-read 120s, it will still be a cache hit.
    clock.advance(10)
    await service.snapshot()

    assert repo.call_count == 1


def test_cache_ttl_spec_default_matches_documented_default() -> None:
    assert CACHE_TTL_SPEC.default == CacheTtlConfig(seconds=DEFAULT_CACHE_TTL_SECONDS)


def test_gemini_quota_ceiling_default_matches_gemini_rate_limiter_hardcoded_default() -> None:
    """Regression guard (design §7.1 #10): if someone changes one without
    the other, this test catches the drift even though nothing consumes the
    config key yet. GeminiRateLimiter.max_requests is private (this ticket
    deliberately does not touch that file -- see design's Status note), so
    the default is read off its constructor signature rather than an
    instance attribute."""
    default_max_requests = (
        inspect.signature(GeminiRateLimiter.__init__).parameters["max_requests"].default
    )
    assert GEMINI_QUOTA_CEILING_SPEC.default.rpm == default_max_requests

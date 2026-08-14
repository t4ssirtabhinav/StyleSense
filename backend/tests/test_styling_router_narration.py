"""Tests for StylingRouter.narrate_candidates_with_decision (SS-020) --
parametrizes the existing test_styling_router.py structure against the new
method: same chain/failover/timeout/degrade logic, proven independently."""

from __future__ import annotations

from typing import Any

from ai.adapters.styling_call import ProviderParseError, ProviderTransientError
from ai.ports.interfaces import NarratedCandidate, NarratedPortfolioResult, StylePreferencesInput
from services.ai_routing_specs import DEFAULT_ROUTING_TABLE, RouterPolicyConfig
from services.styling_router import RoutingContext, StylingRouter


def _metrics(provider: str, model: str) -> Any:
    from ai.adapters.styling_call import StylingCallMetrics

    return StylingCallMetrics(
        provider=provider, model=model, tokens_in=10, tokens_out=5, latency_ms=10
    )


def _fake_narration(source: str) -> NarratedPortfolioResult:
    return NarratedPortfolioResult(
        narrations=[NarratedCandidate(outfit_fingerprint="fp1", rationale="x")],
        language="en",
        source=source,  # type: ignore[arg-type]
    )


class _FakeMeteredProvider:
    def __init__(self, outcomes: list[Any], *, provider: str, model: str) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self._provider = provider
        self._model = model
        self.last_weather: dict[str, Any] | None = None

    async def suggest_outfits_with_metrics(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> Any:
        raise NotImplementedError

    async def narrate_candidates_with_metrics(
        self,
        candidates: list[dict[str, object]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        weather: dict[str, Any] | None = None,
    ) -> Any:
        self.calls += 1
        self.last_weather = weather
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return _fake_narration(self._provider), _metrics(self._provider, self._model)


class _FakeRegistry:
    def __init__(self, adapters: dict[tuple[str, str], Any]) -> None:
        self._adapters = adapters

    def get(self, provider: str, model: str) -> Any:
        return self._adapters.get((provider, model))


class _FakeQuota:
    async def try_reserve(self, provider: str, *, estimated_tokens: int) -> bool:
        return True

    async def record_usage(self, provider: str, *, tokens_in: int, tokens_out: int) -> None:
        pass


class _FakeMonitor:
    def __init__(self) -> None:
        self.records: list[tuple[Any, str]] = []

    def record(self, decision: Any, outcome: str) -> None:
        self.records.append((decision, outcome))


class _FakeFallback:
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.calls = 0
        self.last_weather: dict[str, Any] | None = None

    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> Any:
        raise NotImplementedError

    async def narrate_candidates(
        self,
        candidates: list[dict[str, object]],
        *,
        occasion: str,
        preferences: StylePreferencesInput,
        max_suggestions: int,
        weather: dict[str, Any] | None = None,
    ) -> NarratedPortfolioResult:
        self.calls += 1
        self.last_weather = weather
        if self.raises:
            raise RuntimeError("fallback broke")
        return _fake_narration("rules_only")


def _router(
    *,
    adapters: dict[tuple[str, str], Any],
    fallback: Any = None,
    quota: Any = None,
) -> StylingRouter:
    return StylingRouter(
        registry=_FakeRegistry(adapters),
        routing_table=DEFAULT_ROUTING_TABLE,
        policy=RouterPolicyConfig(attempt_timeout_seconds=2.0, total_deadline_seconds=5.0),
        quota=quota or _FakeQuota(),
        monitor=_FakeMonitor(),
        context=RoutingContext(user_id="user-1"),
        fallback=fallback,
    )


async def test_weather_forwarded_to_the_chain_call() -> None:
    provider = _FakeMeteredProvider([], provider="gemini", model="gemini-3.1-flash-lite")
    router = _router(adapters={("gemini", "gemini-3.1-flash-lite"): provider})
    weather = {
        "city": "Mumbai",
        "temp_c": 28.0,
        "condition": "clear",
        "humidity": 60,
        "is_heavy_rain": False,
    }

    await router.narrate_candidates_with_decision(
        [],
        occasion="office",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
        weather=weather,
    )
    assert provider.last_weather == weather


async def test_weather_forwarded_to_the_degrade_fallback() -> None:
    gemini = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-3.1-flash-lite"
    )
    claude = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-sonnet-5"
    )
    fallback = _FakeFallback()
    router = _router(
        adapters={
            ("gemini", "gemini-3.1-flash-lite"): gemini,
            ("claude", "claude-sonnet-5"): claude,
        },
        fallback=fallback,
    )
    weather = {
        "city": "Mumbai",
        "temp_c": 28.0,
        "condition": "clear",
        "humidity": 60,
        "is_heavy_rain": False,
    }

    await router.narrate_candidates_with_decision(
        [],
        occasion="office",
        preferences=StylePreferencesInput(),
        max_suggestions=5,
        weather=weather,
    )
    assert fallback.last_weather == weather


async def test_success_on_first_provider_returns_result_and_decision() -> None:
    provider = _FakeMeteredProvider([], provider="gemini", model="gemini-3.1-flash-lite")
    router = _router(adapters={("gemini", "gemini-3.1-flash-lite"): provider})

    result, decision = await router.narrate_candidates_with_decision(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.source == "gemini"
    assert decision.provider == "gemini"
    assert provider.calls == 1


async def test_parse_error_retries_same_provider_then_succeeds() -> None:
    provider = _FakeMeteredProvider(
        [ProviderParseError("bad json")], provider="gemini", model="gemini-3.1-flash-lite"
    )
    router = _router(adapters={("gemini", "gemini-3.1-flash-lite"): provider})

    result, _decision = await router.narrate_candidates_with_decision(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.source == "gemini"
    assert provider.calls == 2  # one failed parse + one retry


async def test_transient_error_fails_over_to_next_provider_in_chain() -> None:
    gemini = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-3.1-flash-lite"
    )
    claude = _FakeMeteredProvider([], provider="claude", model="claude-sonnet-5")
    router = _router(
        adapters={
            ("gemini", "gemini-3.1-flash-lite"): gemini,
            ("claude", "claude-sonnet-5"): claude,
        }
    )

    result, decision = await router.narrate_candidates_with_decision(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.source == "claude"
    assert decision.provider == "gemini"  # original decision, not the failover hop


async def test_both_providers_fail_degrades_to_fallback_never_raises() -> None:
    gemini = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-3.1-flash-lite"
    )
    claude = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-sonnet-5"
    )
    fallback = _FakeFallback()
    router = _router(
        adapters={
            ("gemini", "gemini-3.1-flash-lite"): gemini,
            ("claude", "claude-sonnet-5"): claude,
        },
        fallback=fallback,
    )

    result, _decision = await router.narrate_candidates_with_decision(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.source == "rules_only"
    assert fallback.calls == 1


async def test_fallback_itself_raising_still_returns_valid_empty_result_never_raises() -> None:
    gemini = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-3.1-flash-lite"
    )
    claude = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-sonnet-5"
    )
    fallback = _FakeFallback(raises=True)
    router = _router(
        adapters={
            ("gemini", "gemini-3.1-flash-lite"): gemini,
            ("claude", "claude-sonnet-5"): claude,
        },
        fallback=fallback,
    )

    result, _decision = await router.narrate_candidates_with_decision(
        [], occasion="office", preferences=StylePreferencesInput(), max_suggestions=5
    )
    assert result.narrations == []
    assert result.source == "rules_only"

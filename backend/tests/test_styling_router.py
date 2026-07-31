"""Tests for backend/services/styling_router.py (SS-028 design §11)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from ai.adapters.styling_call import (
    ProviderParseError,
    ProviderTransientError,
    StylingCallMetrics,
)
from ai.ports.interfaces import (
    IStylingProvider,
    OutfitSuggestionItem,
    OutfitSuggestionResult,
    StylePreferencesInput,
)
from services.ai_routing_specs import (
    DEFAULT_ROUTING_TABLE,
    Route,
    RouterPolicyConfig,
    RoutingRule,
    RoutingTableConfig,
)
from services.provider_quota import ProviderQuotaTracker
from services.routing_mix_monitor import RoutingMixMonitor
from services.styling_router import RoutingContext, StylingRouter, resolve_route

# ---------------------------------------------------------------------------
# resolve_route() -- pure, no async
# ---------------------------------------------------------------------------


def _ctx(**kwargs: Any) -> RoutingContext:
    return RoutingContext(user_id="user-1", **kwargs)


def test_no_context_signals_resolve_to_default_everyday_route() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx())
    assert decision.provider == "gemini"
    assert decision.cost_class == "everyday"
    assert decision.reason == "default_everyday"


def test_atelier_tier_resolves_high_stakes() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx(tier="atelier"))
    assert decision.cost_class == "high_stakes"
    assert decision.reason == "tier_atelier"


def test_is_first_suggestion_resolves_high_stakes() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx(is_first_suggestion=True))
    assert decision.cost_class == "high_stakes"
    assert decision.reason == "first_ever_suggestion"


def test_wedding_guest_occasion_resolves_high_stakes() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx(occasion="wedding_guest"))
    assert decision.cost_class == "high_stakes"
    assert decision.reason == "high_stakes_occasion"


def test_festival_occasion_kind_resolves_high_stakes() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx(occasion_kind="festival"))
    assert decision.cost_class == "high_stakes"
    assert decision.reason == "high_stakes_occasion_kind"


def test_puja_religious_occasion_kind_stays_everyday_pinning_b6() -> None:
    decision = resolve_route(DEFAULT_ROUTING_TABLE, _ctx(occasion_kind="religious"))
    assert decision.cost_class == "everyday"
    assert decision.reason == "default_everyday"


def test_rule_order_decides_when_two_rules_match() -> None:
    decision = resolve_route(
        DEFAULT_ROUTING_TABLE, _ctx(tier="atelier", occasion="wedding_guest")
    )
    assert decision.reason == "tier_atelier"  # tier rule listed first


def test_unknown_when_field_skips_only_that_rule() -> None:
    table = RoutingTableConfig(
        default=Route(provider="gemini", model="g1", cost_class="everyday", reason="default"),
        rules=[
            RoutingRule(
                when={"nonexistent_field": ["x"]},
                route=Route(provider="claude", model="c1", cost_class="high_stakes", reason="bad_rule"),
            ),
            RoutingRule(
                when={"tier": ["atelier"]},
                route=Route(provider="claude", model="c2", cost_class="high_stakes", reason="good_rule"),
            ),
        ],
        failover={},
    )
    decision = resolve_route(table, _ctx(tier="atelier"))
    assert decision.reason == "good_rule"


async def test_malformed_stored_table_falls_back_to_coded_default_routing() -> None:
    from adapters.interfaces import IAppConfigRepository
    from services.ai_routing_specs import AI_STYLING_ROUTING_TABLE_SPEC
    from services.app_config import AppConfigService

    class _FakeRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict:
            return {AI_STYLING_ROUTING_TABLE_SPEC.key: {"not": "a valid table"}}

    service = AppConfigService(_FakeRepo())
    snapshot = await service.snapshot()
    table = service.read(snapshot, AI_STYLING_ROUTING_TABLE_SPEC)

    decision = resolve_route(table, _ctx())
    assert decision.reason == "default_everyday"


# ---------------------------------------------------------------------------
# StylingRouter -- the attempt ladder, with fake providers
# ---------------------------------------------------------------------------


def _metrics(provider: str, model: str, latency_ms: int = 10) -> StylingCallMetrics:
    return StylingCallMetrics(
        provider=provider, model=model, tokens_in=10, tokens_out=5, latency_ms=latency_ms
    )


def _fake_result(source: str) -> OutfitSuggestionResult:
    return OutfitSuggestionResult(
        user_id="",
        suggestions=[OutfitSuggestionItem(item_category="x", label="y", rationale="z")],
        generated_at=datetime.now(UTC).isoformat(),
        is_personalized=True,
        source=source,  # type: ignore[arg-type]
    )


class _FakeMeteredProvider:
    def __init__(self, outcomes: list[Any], *, provider: str, model: str) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0
        self._provider = provider
        self._model = model

    async def suggest_outfits_with_metrics(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> tuple[OutfitSuggestionResult, StylingCallMetrics]:
        self.calls += 1
        if self._outcomes:
            outcome = self._outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome
        return _fake_result(self._provider), _metrics(self._provider, self._model)


class _FakeRegistry:
    def __init__(self, adapters: dict[tuple[str, str], Any]) -> None:
        self._adapters = adapters
        self.get_calls: list[tuple[str, str]] = []

    def get(self, provider: str, model: str) -> Any:
        self.get_calls.append((provider, model))
        return self._adapters.get((provider, model))


class _FakeQuota:
    def __init__(self, deny_providers: set[str] | None = None) -> None:
        self._deny = deny_providers or set()
        self.reserve_calls: list[str] = []
        self.usage_calls: list[tuple[str, int, int]] = []

    async def try_reserve(self, provider: str, *, estimated_tokens: int) -> bool:
        self.reserve_calls.append(provider)
        return provider not in self._deny

    async def record_usage(self, provider: str, *, tokens_in: int, tokens_out: int) -> None:
        self.usage_calls.append((provider, tokens_in, tokens_out))


class _FakeMonitor:
    def __init__(self) -> None:
        self.records: list[tuple[Any, str]] = []

    def record(self, decision: Any, outcome: str) -> None:
        self.records.append((decision, outcome))


class _FakeFallback(IStylingProvider):
    def __init__(self, *, raises: bool = False) -> None:
        self.raises = raises
        self.calls = 0

    async def suggest_outfits(
        self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
    ) -> OutfitSuggestionResult:
        self.calls += 1
        if self.raises:
            raise RuntimeError("fallback broke")
        return _fake_result("mock")


def _table(failover: dict[str, list[str]] | None = None) -> RoutingTableConfig:
    return RoutingTableConfig(
        default=Route(provider="gemini", model="gemini-model", cost_class="everyday", reason="default_everyday"),
        # A never-matching rule solely to register claude's model in the
        # provider->model map _build_chain/_provider_model_map derive from
        # the table (mirrors the shipped table's real shape, where every
        # provider that can appear in `failover` also owns a route
        # somewhere in `default`/`rules`).
        rules=[
            RoutingRule(
                when={"tier": ["_never_matches_"]},
                route=Route(provider="claude", model="claude-model", cost_class="high_stakes", reason="unused"),
            )
        ],
        failover=failover if failover is not None else {"gemini": ["claude"], "claude": ["gemini"]},
    )


def _policy(**overrides: Any) -> RouterPolicyConfig:
    return RouterPolicyConfig(**overrides)


def _router(
    *,
    registry: _FakeRegistry,
    table: RoutingTableConfig,
    policy: RouterPolicyConfig,
    quota: _FakeQuota | None = None,
    monitor: _FakeMonitor | None = None,
    fallback: IStylingProvider | None = None,
    clock: Any = None,
) -> StylingRouter:
    return StylingRouter(
        registry=registry,
        routing_table=table,
        policy=policy,
        quota=quota or _FakeQuota(),
        monitor=monitor or _FakeMonitor(),
        context=_ctx(),
        fallback=fallback,
        clock=clock,
    )


async def test_primary_succeeds_one_attempt_no_failover() -> None:
    provider = _FakeMeteredProvider([], provider="gemini", model="gemini-model")

    registry = _FakeRegistry({("gemini", "gemini-model"): provider})
    router = _router(registry=registry, table=_table(), policy=_policy())

    result, decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert result.source == "gemini"
    assert provider.calls == 1
    assert decision.provider == "gemini"


async def test_parse_error_retries_same_provider_then_fails_over_to_secondary() -> None:
    gemini_provider = _FakeMeteredProvider(
        [ProviderParseError("bad"), ProviderParseError("bad again")],
        provider="gemini",
        model="gemini-model",
    )
    claude_provider = _FakeMeteredProvider([], provider="claude", model="claude-model")

    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    table = RoutingTableConfig(
        default=Route(provider="gemini", model="gemini-model", cost_class="everyday", reason="default_everyday"),
        rules=[
            RoutingRule(
                when={"tier": ["atelier"]},
                route=Route(provider="claude", model="claude-model", cost_class="high_stakes", reason="x"),
            )
        ],
        failover={"gemini": ["claude"]},
    )
    router = _router(registry=registry, table=table, policy=_policy(parse_retry_attempts=1))

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert gemini_provider.calls == 2  # one same-provider parse retry
    assert claude_provider.calls == 1
    assert result.source == "claude"


async def test_local_quota_exhaustion_skips_straight_to_secondary_without_calling_primary() -> None:
    gemini_provider = _FakeMeteredProvider([], provider="gemini", model="gemini-model")
    claude_provider = _FakeMeteredProvider([], provider="claude", model="claude-model")
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    quota = _FakeQuota(deny_providers={"gemini"})
    router = _router(registry=registry, table=_table(), policy=_policy(), quota=quota)

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert gemini_provider.calls == 0
    assert claude_provider.calls == 1
    assert result.source == "claude"


async def test_both_providers_fail_returns_fallback_degraded_no_exception() -> None:
    gemini_provider = _FakeMeteredProvider([ProviderTransientError("down")], provider="gemini", model="gemini-model")
    claude_provider = _FakeMeteredProvider([ProviderTransientError("down")], provider="claude", model="claude-model")
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    fallback = _FakeFallback()
    monitor = _FakeMonitor()
    router = _router(
        registry=registry, table=_table(), policy=_policy(), fallback=fallback, monitor=monitor
    )

    result, decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert fallback.calls == 1
    assert result.source == "mock"
    outcomes = [o for _d, o in monitor.records]
    assert "degraded" in outcomes


async def test_fallback_itself_raising_still_returns_a_valid_empty_result_no_raise() -> None:
    gemini_provider = _FakeMeteredProvider([ProviderTransientError("down")], provider="gemini", model="gemini-model")
    claude_provider = _FakeMeteredProvider([ProviderTransientError("down")], provider="claude", model="claude-model")
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    fallback = _FakeFallback(raises=True)
    router = _router(registry=registry, table=_table(), policy=_policy(), fallback=fallback)

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert result.suggestions == []
    assert result.is_personalized is False


async def test_deadline_exhausted_before_second_provider_degrades_without_calling_it() -> None:
    gemini_provider = _FakeMeteredProvider([ProviderTransientError("down")], provider="gemini", model="gemini-model")
    claude_provider = _FakeMeteredProvider([], provider="claude", model="claude-model")
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )

    clock_value = [0.0]

    def clock() -> float:
        return clock_value[0]

    # attempt_timeout_seconds=5, total_deadline_seconds clamps to >= 5 --
    # advance the clock past the deadline right after the first call fails.
    policy = _policy(attempt_timeout_seconds=5.0, total_deadline_seconds=5.0)

    # Advances the clock as a side effect of its call, so the deadline check
    # before the NEXT provider observes it as exhausted.
    class _AdvancingProvider(_FakeMeteredProvider):
        async def suggest_outfits_with_metrics(
            self, preferences: StylePreferencesInput, *, max_suggestions: int = 5
        ) -> tuple[OutfitSuggestionResult, StylingCallMetrics]:
            self.calls += 1
            clock_value[0] = 10.0
            raise ProviderTransientError("down")

    gemini_provider = _AdvancingProvider([], provider="gemini", model="gemini-model")
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    router = _router(registry=registry, table=_table(), policy=policy, clock=clock)

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert claude_provider.calls == 0
    assert result.source == "mock"  # degraded


async def test_unknown_provider_name_in_table_does_not_raise_and_fails_over() -> None:
    claude_provider = _FakeMeteredProvider([], provider="claude", model="claude-model")
    registry = _FakeRegistry({("claude", "claude-model"): claude_provider})
    table = RoutingTableConfig(
        default=Route(provider="gemini", model="gemini-model", cost_class="everyday", reason="default_everyday"),
        rules=[
            RoutingRule(
                when={"tier": ["_never_matches_"]},
                route=Route(provider="claude", model="claude-model", cost_class="high_stakes", reason="unused"),
            )
        ],
        failover={"gemini": ["unknown_vendor", "claude"]},
    )
    router = _router(registry=registry, table=table, policy=_policy())

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert result.source == "claude"


async def test_cyclic_failover_attempts_each_provider_at_most_once() -> None:
    gemini_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-model"
    )
    claude_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-model"
    )
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    table = _table(failover={"gemini": ["claude", "gemini"], "claude": ["gemini", "claude"]})
    router = _router(registry=registry, table=table, policy=_policy())

    await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert gemini_provider.calls == 1
    assert claude_provider.calls == 1


async def test_exactly_one_resolve_route_call_per_request_even_across_two_failovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.styling_router as styling_router_module

    gemini_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-model"
    )
    claude_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-model"
    )
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    router = _router(registry=registry, table=_table(), policy=_policy())

    call_count = [0]
    original_resolve_route = styling_router_module.resolve_route

    def _counting_resolve_route(table: Any, context: Any) -> Any:
        call_count[0] += 1
        return original_resolve_route(table, context)

    monkeypatch.setattr(styling_router_module, "resolve_route", _counting_resolve_route)

    await router.suggest_outfits_with_decision(StylePreferencesInput())

    assert call_count[0] == 1


async def test_log_line_carries_every_required_field(caplog: pytest.LogCaptureFixture) -> None:
    provider = _FakeMeteredProvider([], provider="gemini", model="gemini-model")
    registry = _FakeRegistry({("gemini", "gemini-model"): provider})
    router = _router(registry=registry, table=_table(), policy=_policy())

    with caplog.at_level("INFO", logger="services.styling_router"):
        await router.suggest_outfits_with_decision(StylePreferencesInput())

    records = [r for r in caplog.records if r.message == "ai_styling_call"]
    assert len(records) == 1
    record = records[0]
    for field_name in (
        "request_id",
        "user_id",
        "provider",
        "model",
        "cost_class",
        "routing_reason",
        "table_version",
        "attempt",
        "outcome",
        "tokens_in",
        "tokens_out",
        "tokens_used",
        "latency_ms",
        "degraded",
        "config_stale",
    ):
        assert hasattr(record, field_name), f"missing field {field_name}"
    assert getattr(record, "tokens_used") == getattr(record, "tokens_in") + getattr(  # noqa: B009
        record, "tokens_out"
    )
    assert getattr(record, "outcome") == "success"  # noqa: B009


async def test_suggest_outfits_port_method_delegates_and_never_raises() -> None:
    gemini_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="gemini", model="gemini-model"
    )
    claude_provider = _FakeMeteredProvider(
        [ProviderTransientError("down")], provider="claude", model="claude-model"
    )
    registry = _FakeRegistry(
        {
            ("gemini", "gemini-model"): gemini_provider,
            ("claude", "claude-model"): claude_provider,
        }
    )
    router = _router(registry=registry, table=_table(), policy=_policy())

    result = await router.suggest_outfits(StylePreferencesInput())
    assert result.source == "mock"


async def test_real_quota_tracker_end_to_end_with_router() -> None:
    provider = _FakeMeteredProvider([], provider="gemini", model="gemini-model")
    registry = _FakeRegistry({("gemini", "gemini-model"): provider})
    quota = ProviderQuotaTracker({"gemini": (10, 1_000_000)})
    monitor = RoutingMixMonitor()
    router = StylingRouter(
        registry=registry,
        routing_table=_table(),
        policy=_policy(),
        quota=quota,
        monitor=monitor,
        context=_ctx(),
    )

    result, _decision = await router.suggest_outfits_with_decision(StylePreferencesInput())
    assert result.source == "gemini"

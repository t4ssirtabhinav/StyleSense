"""Tests for backend/services/ai_routing_specs.py (SS-028 design §11)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from services.ai_routing_specs import (
    AI_PROVIDER_QUOTA_SPEC,
    AI_ROUTER_POLICY_SPEC,
    AI_STYLING_ROUTING_TABLE_SPEC,
    DEFAULT_PROVIDER_QUOTA,
    DEFAULT_ROUTING_TABLE,
    ProviderQuotaConfig,
    RouterPolicyConfig,
    RoutingTableConfig,
)

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "011_seed_ai_routing_config.sql"
)


def _extract_seeded_jsonb(key: str) -> dict:
    sql = _MIGRATION_PATH.read_text(encoding="utf-8")
    # Each seed row is `('<key>',\n   '{...}'::jsonb, ...`. Extract the
    # first single-quoted JSON blob following the key literal.
    pattern = re.compile(
        r"\('" + re.escape(key) + r"',\s*'(.*?)'::jsonb", re.DOTALL
    )
    match = pattern.search(sql)
    assert match is not None, f"could not find seeded row for key={key!r} in {_MIGRATION_PATH}"
    return json.loads(match.group(1))


def test_default_routing_table_validates_against_its_own_model() -> None:
    assert isinstance(DEFAULT_ROUTING_TABLE, RoutingTableConfig)
    assert DEFAULT_ROUTING_TABLE.default.provider == "gemini"
    assert DEFAULT_ROUTING_TABLE.default.cost_class == "everyday"


def test_default_provider_quota_validates_against_its_own_model() -> None:
    assert isinstance(DEFAULT_PROVIDER_QUOTA, ProviderQuotaConfig)
    assert DEFAULT_PROVIDER_QUOTA.root["gemini"].rpm == 15


def test_default_router_policy_validates_against_its_own_model() -> None:
    assert isinstance(AI_ROUTER_POLICY_SPEC.default, RouterPolicyConfig)
    assert AI_ROUTER_POLICY_SPEC.default.total_deadline_seconds == 12.0


def test_seeded_routing_table_json_parses_to_exactly_the_coded_default() -> None:
    seeded_raw = _extract_seeded_jsonb(AI_STYLING_ROUTING_TABLE_SPEC.key)
    seeded = RoutingTableConfig.model_validate(seeded_raw)
    assert seeded == DEFAULT_ROUTING_TABLE


def test_seeded_provider_quota_json_parses_to_exactly_the_coded_default() -> None:
    seeded_raw = _extract_seeded_jsonb(AI_PROVIDER_QUOTA_SPEC.key)
    seeded = ProviderQuotaConfig.model_validate(seeded_raw)
    assert seeded == DEFAULT_PROVIDER_QUOTA


def test_seeded_router_policy_json_parses_to_exactly_the_coded_default() -> None:
    seeded_raw = _extract_seeded_jsonb(AI_ROUTER_POLICY_SPEC.key)
    seeded = RouterPolicyConfig.model_validate(seeded_raw)
    assert seeded == AI_ROUTER_POLICY_SPEC.default


async def test_malformed_one_key_leaves_the_other_two_readable() -> None:
    from adapters.interfaces import IAppConfigRepository
    from services.app_config import AppConfigService

    class _FakeRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict:
            return {
                AI_STYLING_ROUTING_TABLE_SPEC.key: {"not": "a valid routing table"},
                AI_PROVIDER_QUOTA_SPEC.key: {"gemini": {"rpm": 5, "tpm": 1000}},
                AI_ROUTER_POLICY_SPEC.key: {"attempt_timeout_seconds": 3.0},
            }

    service = AppConfigService(_FakeRepo())
    snapshot = await service.snapshot()

    assert service.read(snapshot, AI_STYLING_ROUTING_TABLE_SPEC) == DEFAULT_ROUTING_TABLE
    assert service.read(snapshot, AI_PROVIDER_QUOTA_SPEC).root["gemini"].rpm == 5
    assert service.read(snapshot, AI_ROUTER_POLICY_SPEC).attempt_timeout_seconds == 3.0


@pytest.mark.parametrize(
    ("field", "raw_value", "expected"),
    [
        ("attempt_timeout_seconds", 0.1, 1.0),
        ("attempt_timeout_seconds", 999.0, 60.0),
        ("parse_retry_attempts", -1, 0),
        ("parse_retry_attempts", 99, 2),
        ("expensive_share_alert_threshold", -0.5, 0.0),
        ("expensive_share_alert_threshold", 5.0, 1.0),
        ("alert_min_sample", 0, 1),
        ("alert_min_sample", 999_999, 10000),
        ("alert_cooldown_seconds", 1, 60),
        ("alert_cooldown_seconds", 999_999, 86400),
        ("provider_outage_alert_seconds", 1, 60),
        ("provider_outage_alert_seconds", 999_999, 86400),
    ],
)
def test_router_policy_clamps_each_field_at_both_ends(
    field: str, raw_value: float, expected: float
) -> None:
    kwargs: dict[str, object] = {field: raw_value}
    policy = RouterPolicyConfig.model_validate(kwargs)
    assert getattr(policy, field) == expected


def test_total_deadline_smaller_than_attempt_timeout_is_clamped_up() -> None:
    policy = RouterPolicyConfig(attempt_timeout_seconds=10.0, total_deadline_seconds=1.0)
    assert policy.total_deadline_seconds >= policy.attempt_timeout_seconds

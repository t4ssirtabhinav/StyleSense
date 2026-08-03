"""Tests for backend/services/price_table.py (SS-029 design §6.2)."""

from __future__ import annotations

import logging
from datetime import date

import pytest

from services.cost_config_specs import _DEFAULT_PRICE_TABLE, AiPriceTableConfig, FxRateRow, PriceRow
from services.price_table import PriceTable

_FX = FxRateRow(effective_from="2026-01-01", rate=84.0, verified=True)


def _config(*prices: PriceRow, fx: list[FxRateRow] | None = None) -> AiPriceTableConfig:
    return AiPriceTableConfig(fx_usd_to_inr=fx or [_FX], prices=list(prices))


def test_resolves_row_with_greatest_effective_from_not_after_date() -> None:
    early = PriceRow(
        provider="p",
        model="m",
        mode="per_call",
        effective_from="2026-01-01",
        usd_per_call=1.0,
        verified=True,
    )
    late = PriceRow(
        provider="p",
        model="m",
        mode="per_call",
        effective_from="2026-06-01",
        usd_per_call=2.0,
        verified=True,
    )
    config = _config(early, late)
    table = PriceTable(config)

    result = table.cost(provider="p", model="m", tokens_in=None, tokens_out=None, at=date(2026, 3, 1))

    # Between the two -- earlier row wins.
    assert result.cost_micropaise == round(1.0 * 84.0 * 100_000_000)


def test_sonnet_5_price_steps_up_on_2026_09_01() -> None:
    table = PriceTable(_DEFAULT_PRICE_TABLE)

    before = table.cost(
        provider="anthropic",
        model="claude-sonnet-5",
        tokens_in=800,
        tokens_out=500,
        at=date(2026, 8, 31),
    )
    after = table.cost(
        provider="anthropic",
        model="claude-sonnet-5",
        tokens_in=800,
        tokens_out=500,
        at=date(2026, 9, 1),
    )

    assert before.unit_price_snapshot["usd_per_mtok_in"] == 2.00
    assert before.unit_price_snapshot["usd_per_mtok_out"] == 10.00
    assert after.unit_price_snapshot["usd_per_mtok_in"] == 3.00
    assert after.unit_price_snapshot["usd_per_mtok_out"] == 15.00
    assert after.cost_micropaise > before.cost_micropaise
    assert before.pricing_status == "priced"
    assert after.pricing_status == "priced"


def test_expired_row_with_no_successor_marks_estimated_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = PriceRow(
        provider="p",
        model="m",
        mode="per_call",
        effective_from="2026-01-01",
        effective_until="2026-03-01",
        usd_per_call=1.0,
        verified=True,
    )
    config = _config(row)
    table = PriceTable(config)

    with caplog.at_level(logging.ERROR):
        result = table.cost(
            provider="p", model="m", tokens_in=None, tokens_out=None, at=date(2026, 4, 1)
        )

    assert result.pricing_status == "estimated"
    assert any(r.message == "ledger_price_row_expired" for r in caplog.records)


def test_unknown_model_returns_unpriced_zero_and_logs_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = _config()
    table = PriceTable(config)

    with caplog.at_level(logging.ERROR):
        result = table.cost(
            provider="nope", model="nope", tokens_in=100, tokens_out=100, at=date(2026, 1, 1)
        )

    assert result.cost_micropaise == 0
    assert result.pricing_status == "unpriced"
    assert any(r.message == "ledger_unpriced_call" for r in caplog.records)


def test_per_token_cost_matches_execution_plan_figure() -> None:
    row = PriceRow(
        provider="gemini",
        model="gemini-2.5-flash-lite",
        mode="per_token",
        effective_from="2026-01-01",
        usd_per_mtok_in=0.10,
        usd_per_mtok_out=0.40,
        verified=True,
    )
    config = _config(row)
    table = PriceTable(config)

    result = table.cost(
        provider="gemini",
        model="gemini-2.5-flash-lite",
        tokens_in=800,
        tokens_out=500,
        at=date(2026, 1, 15),
    )

    # (800/1e6)*0.10 + (500/1e6)*0.40 = 0.00028 USD * 84 = ~0.0235 rupee
    # ~= 2.35 paise, matching the execution plan's ~₹0.024 figure within
    # rounding.
    assert result.cost_micropaise == round(0.00028 * 84.0 * 100_000_000)
    paise = result.cost_micropaise / 1_000_000
    assert 2.0 < paise < 3.0


def test_per_call_pricing_ignores_tokens() -> None:
    row = PriceRow(
        provider="replicate",
        model="bria-rmbg",
        mode="per_call",
        effective_from="2026-01-01",
        usd_per_call=0.0023,
        verified=True,
    )
    config = _config(row)
    table = PriceTable(config)

    with_tokens = table.cost(
        provider="replicate", model="bria-rmbg", tokens_in=99999, tokens_out=99999, at=date(2026, 1, 1)
    )
    without_tokens = table.cost(
        provider="replicate", model="bria-rmbg", tokens_in=None, tokens_out=None, at=date(2026, 1, 1)
    )

    assert with_tokens.cost_micropaise == without_tokens.cost_micropaise
    assert with_tokens.cost_micropaise == round(0.0023 * 84.0 * 100_000_000)


def test_cost_is_exact_integer_micropaise_no_float_drift() -> None:
    row = PriceRow(
        provider="p",
        model="m",
        mode="per_token",
        effective_from="2026-01-01",
        usd_per_mtok_in=0.10,
        usd_per_mtok_out=0.40,
        verified=True,
    )
    config = _config(row)
    table = PriceTable(config)

    unit = table.cost(
        provider="p", model="m", tokens_in=1800, tokens_out=300, at=date(2026, 1, 1)
    ).cost_micropaise

    total = sum(
        table.cost(provider="p", model="m", tokens_in=1800, tokens_out=300, at=date(2026, 1, 1)).cost_micropaise
        for _ in range(10_000)
    )
    assert total == unit * 10_000


def test_fx_rate_is_dated_and_snapshotted() -> None:
    row = PriceRow(
        provider="p",
        model="m",
        mode="per_call",
        effective_from="2026-01-01",
        usd_per_call=1.0,
        verified=True,
    )
    fx_rows = [
        FxRateRow(effective_from="2026-01-01", rate=84.0, verified=True),
        FxRateRow(effective_from="2026-06-01", rate=90.0, verified=True),
    ]
    config = _config(row, fx=fx_rows)
    table = PriceTable(config)

    early = table.cost(provider="p", model="m", tokens_in=None, tokens_out=None, at=date(2026, 3, 1))
    late = table.cost(provider="p", model="m", tokens_in=None, tokens_out=None, at=date(2026, 7, 1))

    assert early.unit_price_snapshot["fx_usd_to_inr"] == 84.0
    assert late.unit_price_snapshot["fx_usd_to_inr"] == 90.0
    assert late.cost_micropaise > early.cost_micropaise


def test_verified_false_row_marks_estimated() -> None:
    table = PriceTable(_DEFAULT_PRICE_TABLE)

    result = table.cost(
        provider="gemini",
        model="gemini-3.5-flash-lite",
        tokens_in=1800,
        tokens_out=300,
        at=date(2026, 1, 15),
    )

    assert result.pricing_status == "estimated"

    bria = table.cost(
        provider="replicate", model="bria-rmbg", tokens_in=None, tokens_out=None, at=date(2026, 1, 15)
    )
    assert bria.pricing_status == "estimated"


def test_estimate_uses_default_tokens_for_reservation() -> None:
    table = PriceTable(_DEFAULT_PRICE_TABLE)

    estimate = table.estimate(
        provider="anthropic", model="claude-sonnet-5", at=date(2026, 3, 1)
    )
    actual = table.cost(
        provider="anthropic",
        model="claude-sonnet-5",
        tokens_in=800,
        tokens_out=500,
        at=date(2026, 3, 1),
    )

    assert estimate.cost_micropaise == actual.cost_micropaise

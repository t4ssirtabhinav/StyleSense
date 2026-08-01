"""``PriceTable`` -- resolves a dated price row for ``(provider, model,
date)``, computes ``cost_micropaise``, and exposes the pre-call reservation
estimate (SS-029 design §2.1/§3.2). Pure, no I/O -- takes an already-read
``AiPriceTableConfig`` (from an ``AppConfigSnapshot`` via
``cost_config_specs.AI_PRICE_TABLE_SPEC``), never fetches config itself.

**Resolution rule (exact, transcribed from design §3.2):** for a call at IST
date ``D``, select rows matching ``(provider, model)`` where
``effective_from <= D``, and take the one with the greatest
``effective_from``. Then:

- no ``effective_until``, or ``D <= effective_until`` -> ``priced`` (unless
  ``verified=False``, which always forces ``estimated`` regardless of date).
- ``effective_until < D`` and no successor row (a later-``effective_from``
  row for the same ``(provider, model)``) exists -> ``estimated``, log
  ``ledger_price_row_expired`` at ERROR. This is the mechanical guard for
  the 2026-08-31 Claude Sonnet 5 pricing cliff.
- no row matches at all -> ``cost_micropaise = 0``, ``unpriced``, log
  ``ledger_unpriced_call`` at ERROR. **Never silently treat an unknown
  model as free.**

Money conversion: ``cost_micropaise = round(usd * fx_rate * 1e8)``
(1 rupee = 100 paise = 100_000_000 micropaise, so USD -> INR -> micropaise
in one step). The resolved FX rate is snapshotted into every result's
``unit_price_snapshot`` alongside the USD rates actually used, so a later
``app_config`` ``UPDATE`` never retroactively rewrites a ledger row already
written (design §3.5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from services.cost_config_specs import AiPriceTableConfig, FxRateRow, PriceRow

logger = logging.getLogger(__name__)

MICROPAISE_PER_RUPEE = 100_000_000
_FALLBACK_FX_RATE = 84.0  # only used if no fx row resolves at all -- defensive, not expected to fire


@dataclass(frozen=True)
class PriceResolution:
    cost_micropaise: int
    pricing_status: Literal["priced", "estimated", "unpriced"]
    price_effective_from: str | None
    unit_price_snapshot: dict[str, Any]


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _resolve_fx_rate(config: AiPriceTableConfig, at: date) -> FxRateRow | None:
    candidates = [row for row in config.fx_usd_to_inr if _parse_date(row.effective_from) <= at]
    if not candidates:
        return None
    return max(candidates, key=lambda row: row.effective_from)


def _resolve_price_row(
    config: AiPriceTableConfig, *, provider: str, model: str, at: date
) -> tuple[PriceRow | None, bool]:
    """Returns ``(selected_row, has_successor)``. ``has_successor`` is True
    when another row exists for the same ``(provider, model)`` with a
    strictly later ``effective_from`` than the selected row -- the signal
    that this pricing gap was actually anticipated by whoever maintains the
    config, not silently abandoned."""
    matching = [
        row for row in config.prices if row.provider == provider and row.model == model
    ]
    eligible = [row for row in matching if _parse_date(row.effective_from) <= at]
    if not eligible:
        return None, False
    selected = max(eligible, key=lambda row: row.effective_from)
    has_successor = any(row.effective_from > selected.effective_from for row in matching)
    return selected, has_successor


def _cost_micropaise(
    row: PriceRow, fx_rate: float, *, tokens_in: int | None, tokens_out: int | None
) -> int:
    if row.mode == "per_call":
        usd = row.usd_per_call or 0.0
    else:
        usd_in = (row.usd_per_mtok_in or 0.0) * ((tokens_in or 0) / 1_000_000)
        usd_out = (row.usd_per_mtok_out or 0.0) * ((tokens_out or 0) / 1_000_000)
        usd = usd_in + usd_out
    return round(usd * fx_rate * MICROPAISE_PER_RUPEE)


def _resolve(
    config: AiPriceTableConfig,
    *,
    provider: str,
    model: str,
    at: date,
    tokens_in: int | None,
    tokens_out: int | None,
) -> PriceResolution:
    row, has_successor = _resolve_price_row(config, provider=provider, model=model, at=at)

    if row is None:
        logger.error(
            "ledger_unpriced_call",
            extra={"provider": provider, "model": model, "at": at.isoformat()},
        )
        return PriceResolution(
            cost_micropaise=0,
            pricing_status="unpriced",
            price_effective_from=None,
            unit_price_snapshot={},
        )

    fx_row = _resolve_fx_rate(config, at)
    fx_rate = fx_row.rate if fx_row is not None else _FALLBACK_FX_RATE
    if fx_row is None:
        logger.warning(
            "ledger_fx_rate_unresolved",
            extra={"provider": provider, "model": model, "at": at.isoformat()},
        )

    expired_with_no_successor = (
        row.effective_until is not None
        and _parse_date(row.effective_until) < at
        and not has_successor
    )
    if expired_with_no_successor:
        logger.error(
            "ledger_price_row_expired",
            extra={
                "provider": provider,
                "model": model,
                "at": at.isoformat(),
                "effective_until": row.effective_until,
            },
        )

    pricing_status: Literal["priced", "estimated", "unpriced"]
    if not row.verified or expired_with_no_successor:
        pricing_status = "estimated"
    else:
        pricing_status = "priced"

    cost_micropaise = _cost_micropaise(row, fx_rate, tokens_in=tokens_in, tokens_out=tokens_out)

    snapshot = {
        "provider": provider,
        "model": model,
        "mode": row.mode,
        "usd_per_mtok_in": row.usd_per_mtok_in,
        "usd_per_mtok_out": row.usd_per_mtok_out,
        "usd_per_call": row.usd_per_call,
        "fx_usd_to_inr": fx_rate,
        "fx_effective_from": fx_row.effective_from if fx_row is not None else None,
        "row_verified": row.verified,
    }

    return PriceResolution(
        cost_micropaise=cost_micropaise,
        pricing_status=pricing_status,
        price_effective_from=row.effective_from,
        unit_price_snapshot=snapshot,
    )


class PriceTable:
    """Constructed with an already-read ``AiPriceTableConfig`` -- one per
    request/task (mirrors ``AppConfigSnapshot``'s "one per request" rule,
    design edge case 16). Never call ``app_config_service.snapshot()``
    itself; the caller passes the resolved config in."""

    def __init__(self, config: AiPriceTableConfig) -> None:
        self._config = config

    def estimate(self, *, provider: str, model: str, at: date) -> PriceResolution:
        """Pre-call reservation estimate. ``per_token`` rows use
        ``default_tokens_in/out`` (you cannot know real token counts before
        the call); ``per_call`` rows need no estimate -- estimate equals
        actual, so reconciliation is a no-op."""
        row, _ = _resolve_price_row(self._config, provider=provider, model=model, at=at)
        default_tokens_in = row.default_tokens_in if row is not None else None
        default_tokens_out = row.default_tokens_out if row is not None else None
        return _resolve(
            self._config,
            provider=provider,
            model=model,
            at=at,
            tokens_in=default_tokens_in,
            tokens_out=default_tokens_out,
        )

    def cost(
        self,
        *,
        provider: str,
        model: str,
        tokens_in: int | None,
        tokens_out: int | None,
        at: date,
    ) -> PriceResolution:
        """Post-call actual cost from real token counts (``per_token``) or
        ignoring tokens entirely (``per_call``)."""
        return _resolve(
            self._config,
            provider=provider,
            model=model,
            at=at,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

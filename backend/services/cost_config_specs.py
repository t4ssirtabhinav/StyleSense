"""SS-029 ``ConfigSpec``s + Pydantic models for the two new ``app_config``
keys this ticket introduces: ``ai_price_table`` and ``ai_cost_budgets``.

Mirrors ``services/app_config_specs.py``'s established shape (SS-026):
every ``ConfigSpec`` carries a hardcoded safe default so a missing/malformed
row degrades to a known-good value, never an exception. Kept in its own
module near the cost-ledger feature rather than growing the SS-026 demo
file, per that file's own "a future domain ticket may add its own specs
file" note.

**Do not restyle the numeric defaults below** -- they are transcribed
verbatim from ``docs/tickets/SS-029-design.md`` §3.2/§3.3, itself
transcribed from ``docs/proposals/EXECUTION-PLAN.md`` §2.2 (dated
``[VERIFIED 2026-07-28]``) and the orchestrator-approved Q3 budget ceilings
(2026-07-30).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from services.app_config import ConfigSpec

PriceMode = Literal["per_token", "per_call"]
PlanTier = Literal["free", "premium", "premium_annual"]


class FxRateRow(BaseModel):
    effective_from: str  # ISO date, e.g. "2026-01-01"
    rate: float
    verified: bool = False


class PriceRow(BaseModel):
    provider: str
    model: str
    mode: PriceMode
    effective_from: str
    effective_until: str | None = None
    usd_per_mtok_in: float | None = None
    usd_per_mtok_out: float | None = None
    usd_per_call: float | None = None
    default_tokens_in: int | None = None
    default_tokens_out: int | None = None
    verified: bool = False


class AiPriceTableConfig(BaseModel):
    """Validates ``app_config.ai_price_table``. See design §3.2's
    "Resolution rule (exact, no ambiguity)" -- resolution logic itself lives
    in ``services/price_table.py``, this module only owns the shape."""

    fx_usd_to_inr: list[FxRateRow] = Field(default_factory=list)
    prices: list[PriceRow] = Field(default_factory=list)


# Coded default -- the exact JSON transcribed verbatim from design §3.2's
# "Config shape" example. This IS the migration seed data too (see
# 012_ai_cost_ledger.sql's sibling app_config INSERT in the same migration
# set -- seeded by the Developer phase's manual verification step, not by
# this file, since app_config rows are data, not schema).
_DEFAULT_PRICE_TABLE = AiPriceTableConfig(
    fx_usd_to_inr=[FxRateRow(effective_from="2026-01-01", rate=84.0, verified=False)],
    prices=[
        PriceRow(
            provider="gemini",
            model="gemini-3.5-flash-lite",
            mode="per_token",
            effective_from="2026-01-01",
            usd_per_mtok_in=0.10,
            usd_per_mtok_out=0.40,
            default_tokens_in=1800,
            default_tokens_out=300,
            verified=False,
        ),
        PriceRow(
            provider="anthropic",
            model="claude-sonnet-5",
            mode="per_token",
            effective_from="2026-01-01",
            effective_until="2026-08-31",
            usd_per_mtok_in=2.00,
            usd_per_mtok_out=10.00,
            default_tokens_in=800,
            default_tokens_out=500,
            verified=True,
        ),
        PriceRow(
            provider="anthropic",
            model="claude-sonnet-5",
            mode="per_token",
            effective_from="2026-09-01",
            usd_per_mtok_in=3.00,
            usd_per_mtok_out=15.00,
            default_tokens_in=800,
            default_tokens_out=500,
            verified=True,
        ),
        PriceRow(
            provider="replicate",
            model="bria-rmbg",
            mode="per_call",
            effective_from="2026-01-01",
            usd_per_call=0.0023,
            verified=False,
        ),
    ],
)

AI_PRICE_TABLE_SPEC: ConfigSpec[AiPriceTableConfig] = ConfigSpec(
    key="ai_price_table", model=AiPriceTableConfig, default=_DEFAULT_PRICE_TABLE
)


class TierBudget(BaseModel):
    """One tier's ceilings, in **paise** (matching the AC's literal unit) --
    ``daily_micropaise``/``monthly_micropaise`` below convert to the
    internal micropaise unit the gate/Redis actually operate in (design
    §3.1)."""

    daily_paise: int
    monthly_paise: int
    enforce: bool = True
    fail_open: bool = False

    @property
    def daily_micropaise(self) -> int:
        return self.daily_paise * 1_000_000

    @property
    def monthly_micropaise(self) -> int:
        return self.monthly_paise * 1_000_000


class AiCostBudgetsConfig(BaseModel):
    """Validates ``app_config.ai_cost_budgets``. Values per design §3.3,
    approved 2026-07-30 (Q3 resolved) -- free ₹5/day·₹25/mo (fail_open=False),
    paying ₹50/day·₹500/mo (fail_open=True)."""

    free: TierBudget = TierBudget(daily_paise=500, monthly_paise=2500, enforce=True, fail_open=False)
    premium: TierBudget = TierBudget(
        daily_paise=5000, monthly_paise=50000, enforce=True, fail_open=True
    )
    premium_annual: TierBudget = TierBudget(
        daily_paise=5000, monthly_paise=50000, enforce=True, fail_open=True
    )

    def for_tier(self, tier: str | None) -> TierBudget:
        """A ``NULL``/missing/unrecognised tier normalises to ``free``
        (fail-closed direction) -- design §3.3/edge case 8. Never treat an
        unknown tier as paying."""
        normalized = tier if tier in ("free", "premium", "premium_annual") else "free"
        return getattr(self, normalized)


AI_COST_BUDGETS_SPEC: ConfigSpec[AiCostBudgetsConfig] = ConfigSpec(
    key="ai_cost_budgets", model=AiCostBudgetsConfig, default=AiCostBudgetsConfig()
)

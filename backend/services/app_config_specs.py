"""Demo-only ``ConfigSpec``s for SS-026's seeded keys (design §3.6), plus
SS-038's first real consumer spec.

Proves the ``app_config``/``AppConfigService`` substrate against real
acceptance criteria; wires NO real consumer. A future domain ticket may add
its own specs file near its own service rather than growing this one
indefinitely (flagged, not decided, in the design doc's §10).

``GEMINI_QUOTA_CEILING_SPEC``'s coded default (``rpm=15``) matches
``backend/services/gemini_rate_limiter.py``'s CURRENT hardcoded default
exactly -- if this key is ever read and the row is missing/malformed,
behaviour is IDENTICAL to today's, never a silent regression. Retires
``BL-076`` in spirit only: the mechanism exists, the constant does not move
in this ticket (that is SS-028's job).

``NEAR_WHITE_THRESHOLD_SPEC`` (SS-038, resolves ``BL-111``) moves the HSV
near-white/cream/ivory exclusion thresholds from a Python literal
(``styling_rules_defaults.NEAR_WHITE_VALUE_THRESHOLD``/
``NEAR_WHITE_SATURATION_THRESHOLD``) into an ``app_config`` row, coded
default IDENTICAL to those constants' current values -- a missing/malformed
row degrades to exactly today's behaviour, same SS-026 pattern as
``GEMINI_QUOTA_CEILING_SPEC``. ``engine_v2_eligibility.resolve_near_white_thresholds``
is the real consumer; see ``supabase/migrations/017_seed_engine_v2_near_white_config.sql``
for the seeded row and ``styling_rules_types.StylingRulesOverride``'s
``near_white_value_threshold``/``near_white_saturation_threshold`` fields for
the per-occasion override path.
"""

from __future__ import annotations

from pydantic import BaseModel

from services.app_config import ConfigSpec


class GeminiQuotaCeilingConfig(BaseModel):
    rpm: int = 15


GEMINI_QUOTA_CEILING_SPEC: ConfigSpec[GeminiQuotaCeilingConfig] = ConfigSpec(
    key="gemini_quota_ceiling_rpm",
    model=GeminiQuotaCeilingConfig,
    default=GeminiQuotaCeilingConfig(),
)


class NearWhiteThresholdConfig(BaseModel):
    """Coded defaults transcribed verbatim from
    ``styling_rules_defaults.NEAR_WHITE_VALUE_THRESHOLD``/
    ``NEAR_WHITE_SATURATION_THRESHOLD`` -- unchanged by SS-038 per the
    user's 2026-08-06 sign-off (keep the aggressive default, make it
    tunable, do not narrow it)."""

    value_threshold: float = 0.92
    saturation_threshold: float = 0.12


NEAR_WHITE_THRESHOLD_SPEC: ConfigSpec[NearWhiteThresholdConfig] = ConfigSpec(
    key="near_white_threshold",
    model=NearWhiteThresholdConfig,
    default=NearWhiteThresholdConfig(),
)

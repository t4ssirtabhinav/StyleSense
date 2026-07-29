"""Demo-only ``ConfigSpec``s for SS-026's seeded keys (design §3.6).

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

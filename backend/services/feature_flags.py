"""PostHog feature flags — backend (SS-026).

First-ever backend PostHog usage in this repo. Verified before writing this
file against the actually-installed ``posthog==7.32.0`` package (design §5
flagged the original sketch ``[trained-knowledge, unverified]`` -- this is
that verification, not an assumption): ``Posthog(project_api_key,
host=...)`` is the real client-instance constructor (first positional arg
is named ``project_api_key`` in the installed package, passed positionally
here so the name doesn't matter), and
``Posthog.feature_enabled(key, distinct_id, ...) -> bool | None`` is the
real method signature -- both match this file's usage exactly, no cast or
workaround needed (``BL-091`` closed the "which shape" half of its own
question; the personal-API-key/local-evaluation-latency half is
unconfirmed and stays open).

Deliberately a **categorically different mechanism from ``app_config``**
(design §1): user-targeted, cohort-scoped, eventually-consistent-by-nature,
vendor-owned -- never merged with the server-side/atomic/auditable
``app_config`` substrate.

Same fail-safe posture as ``mobile/lib/analytics.ts``'s ``initAnalytics()``
(no-op when the credential is absent) and ``backend/main.py``'s existing
``if sentry_dsn: sentry_sdk.init(...)`` guard.

**Unlike ``AppConfigService``, ``feature_flag_service`` is constructed at
import time** (mirrors ``main.py``'s own Sentry-init precedent, not
``AppConfigService``'s fully-lazy pattern) -- acceptable because (a)
nothing in this ticket imports this module from ``main.py`` or any router
(no consumer yet, same as ``app_config``), so it stays entirely dormant
until a future ticket wires it in, and (b) the ticket's explicit "never a
startup dependency" requirement was stated for ``app_config`` specifically,
not PostHog flags. A deliberate, minor asymmetry, not an oversight.
"""

from __future__ import annotations

import logging
import os

from posthog import Posthog

logger = logging.getLogger(__name__)

DEFAULT_POSTHOG_HOST = "https://us.i.posthog.com"


class FeatureFlagKey:
    """Mirrors mobile's ``constants/featureFlags.ts``. Kept in sync BY HAND
    -- no shared codegen exists between the two lists (``BL-092``)."""

    PAYWALL_COPY_VARIANT = "paywall_copy_variant"


class FeatureFlagService:
    def __init__(self) -> None:
        api_key = os.getenv("POSTHOG_API_KEY")
        host = os.getenv("POSTHOG_HOST", DEFAULT_POSTHOG_HOST)
        self._client: Posthog | None = Posthog(api_key, host=host) if api_key else None

    def is_enabled(self, flag_key: str, distinct_id: str, *, default: bool = False) -> bool:
        """Never raises -- a flags outage must never break the caller. No
        credential configured -> ``default`` with no client constructed at
        all."""
        if self._client is None:
            return default
        try:
            result = self._client.feature_enabled(flag_key, distinct_id)
        except Exception as exc:  # noqa: BLE001 -- a flags outage must never break the caller
            logger.warning("feature_flag_check_failed", extra={"flag": flag_key, "error": str(exc)})
            return default
        return bool(result) if result is not None else default


# Constructed at import time -- see module docstring for why this is
# acceptable here but not for AppConfigService. No consumer imports this
# module yet.
feature_flag_service = FeatureFlagService()

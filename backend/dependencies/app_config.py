"""Shared ``Depends()`` wrapper around ``services.app_config.app_config_service``
(SS-028).

Per ``services/app_config.py``'s own forward-compat note: a route must call
``app_config_service.snapshot()`` exactly ONCE per request, then read every
key off that one snapshot -- never re-fetch mid-request. Both
``routers/outfit_suggestions.py`` (new consumer, SS-028) and
``routers/wardrobe.py`` (retrofitted, SS-028, closes ``BL-076``) depend on
this single function rather than each defining their own, so there is
exactly one place that owns "one snapshot per request".

Zero I/O at import -- ``app_config_service`` is already a zero-I/O
module-scope singleton (see ``services/app_config.py``); this module adds
no further state.
"""

from __future__ import annotations

from services.app_config import AppConfigSnapshot, app_config_service


async def get_app_config_snapshot() -> AppConfigSnapshot:
    return await app_config_service.snapshot()

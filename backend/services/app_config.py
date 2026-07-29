"""Runtime config substrate — the single typed accessor for ``app_config``
(SS-026).

Every requirement in the raw ticket maps onto this module:

- Reads go through exactly one accessor (``AppConfigService``) -- never a
  raw table read scattered across services.
- ``snapshot()`` is async, TTL-cached, and NEVER RAISES: a cache-miss/expiry
  refetch failure falls back to the last-good snapshot (marked stale) or an
  empty one if there has never been a successful read.
- ``read(snapshot, spec)`` is pure, no I/O, and validates every value
  against a per-key Pydantic model. A missing key logs at INFO and returns
  the coded default (routine -- most keys won't be seeded by every ticket);
  a malformed value logs at ERROR and returns the coded default (a real
  data-quality problem in a stored row). One bad row never breaks any other
  key's read.
- A caller takes exactly ONE ``AppConfigSnapshot`` per request/task and
  reads every value from it -- this is what satisfies "a single request
  must see one consistent config view", not re-fetching mid-request.
- The cache TTL is itself a config key (``config_cache_ttl_seconds``),
  self-referentially adopted after each successful fetch, with two
  independent defenses against a bad value: a shape/type failure never
  reaches the numeric clamp (``read()`` already fell back to the coded
  default first); a shape-valid-but-extreme number is clamped to
  ``[5, 3600]`` seconds, never trusted raw.
- Config NEVER touches boot. The module-scope singleton below is
  constructed with ZERO I/O (mirrors ``routers/wardrobe.py``'s
  ``_occasion_normalizer`` pattern exactly) -- nothing calls
  ``.snapshot()`` until a real consumer (SS-028+) actually reads a value,
  and ``main.py`` never imports this module. Stronger than graceful
  degradation: there is no boot-time coupling to break.

**Forward-compat note for SS-027/028/029 (not built here):** a future
router wraps ``app_config_service`` in a FastAPI ``Depends()`` exactly as
``routers/wardrobe.py::get_occasion_normalizer()`` wraps
``_occasion_normalizer`` -- call ``.snapshot()`` once per request (e.g. as
its own ``Depends()``), then pass that snapshot into every ``.read()`` call
for that request. A route must never call ``app_config_service.snapshot()``
more than once per request.

**Known limitation (flagged, same class as ``OccasionNormalizer.get_registry()``'s
existing precedent in this exact codebase):** two concurrent ``snapshot()``
calls when the cache has just expired can both trigger a ``fetch_all()`` --
no single-flight lock. Not a correctness bug, just occasionally-redundant
work.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from adapters.app_config_repository import SupabaseAppConfigRepository
from adapters.interfaces import IAppConfigRepository

logger = logging.getLogger(__name__)

MIN_CACHE_TTL_SECONDS = 5.0
MAX_CACHE_TTL_SECONDS = 3600.0
DEFAULT_CACHE_TTL_SECONDS = 60.0  # matches OccasionNormalizer's own precedent exactly

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class ConfigSpec(Generic[T]):
    """One key's contract: its Pydantic model, its hardcoded safe default
    (required by AC #4), and whether it is informationally intended to be
    ``client_visible`` (the DB ``scope`` column is the real enforcement
    point -- this flag documents intent only, it enforces nothing)."""

    key: str
    model: type[T]
    default: T
    client_visible: bool = False


@dataclass(frozen=True)
class AppConfigSnapshot:
    """Immutable, point-in-time. A caller fetches ONE of these per
    request/task and calls ``read()`` against it repeatedly -- this is what
    satisfies "a single request must see one consistent config snapshot".
    Never re-fetched mid-lifetime; never mutated."""

    values: dict[str, Any] = field(default_factory=dict)
    fetched_at: float = 0.0
    stale: bool = False  # True = this snapshot is a fetch-failure fallback


class CacheTtlConfig(BaseModel):
    seconds: float = DEFAULT_CACHE_TTL_SECONDS


CACHE_TTL_SPEC: ConfigSpec[CacheTtlConfig] = ConfigSpec(
    key="config_cache_ttl_seconds", model=CacheTtlConfig, default=CacheTtlConfig()
)


def _clamp_ttl(seconds: float) -> float:
    """Requirement #4: a bad TTL value must NEVER make config unreachable.
    Two independent defenses layer here: (1) a value that fails Pydantic
    validation entirely (wrong shape/type) never reaches this function --
    ``read()`` already fell back to ``CACHE_TTL_SPEC.default`` before calling
    it; (2) a value that parses fine but is an extreme/degenerate number (0,
    negative, NaN, a week) is clamped here, never trusted raw."""
    try:
        f = float(seconds)
    except (TypeError, ValueError):
        return DEFAULT_CACHE_TTL_SECONDS
    if f != f:  # NaN
        return DEFAULT_CACHE_TTL_SECONDS
    return max(MIN_CACHE_TTL_SECONDS, min(MAX_CACHE_TTL_SECONDS, f))


class AppConfigService:
    def __init__(
        self,
        repository: IAppConfigRepository,
        *,
        initial_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self._repository = repository
        self._ttl_seconds = _clamp_ttl(initial_ttl_seconds)
        self._snapshot: AppConfigSnapshot | None = None

    async def snapshot(self) -> AppConfigSnapshot:
        """Never raises. Cache-hit: return the held snapshot while fresh.
        Cache-miss/expired: refetch; on failure, fall back to the last-good
        snapshot (marked stale) or an empty one if there has never been a
        successful read -- ``read()`` then serves every key's coded
        default."""
        now = time.monotonic()
        if self._snapshot is not None and (now - self._snapshot.fetched_at) < self._ttl_seconds:
            return self._snapshot
        try:
            values = await self._repository.fetch_all()
        except Exception as exc:  # noqa: BLE001 -- config read must never break the caller
            logger.warning("app_config_fetch_failed", extra={"error": str(exc)})
            if self._snapshot is not None:
                return dataclasses.replace(self._snapshot, stale=True)
            return AppConfigSnapshot(values={}, fetched_at=now, stale=True)
        snap = AppConfigSnapshot(values=values, fetched_at=now, stale=False)
        self._snapshot = snap
        # Self-referential TTL: adopt the freshly-read cache-TTL value
        # (clamped) as the interval for the NEXT refresh cycle. This is what
        # makes "the cache TTL is itself a config key" actually live-tunable
        # without ever risking unreachability.
        self._ttl_seconds = _clamp_ttl(self.read(snap, CACHE_TTL_SPEC).seconds)
        return snap

    def read(self, snapshot: AppConfigSnapshot, spec: ConfigSpec[T]) -> T:
        """Pure, no I/O, never raises. MISSING key -> default, logged at
        INFO (routine -- most keys won't be seeded by every ticket).
        MALFORMED value (wrong shape for ``spec.model``) -> default, logged
        at ERROR (a real data-quality problem in a stored row) -- per the
        ticket's own "logs at error level" wording. Never touches any OTHER
        key's value -- one bad row cannot break the rest of the read."""
        raw = snapshot.values.get(spec.key)
        if raw is None:
            logger.info("app_config_key_missing", extra={"key": spec.key})
            return spec.default
        try:
            return spec.model.model_validate(raw)
        except ValidationError as exc:
            logger.error("app_config_value_invalid", extra={"key": spec.key, "error": str(exc)})
            return spec.default


# Module-scope singleton, constructed at import with ZERO I/O (mirrors
# routers/wardrobe.py's `_occasion_normalizer` pattern exactly) -- this is
# what makes "config is never a startup dependency" true even stronger than
# graceful degradation: nothing calls .snapshot() until a real consumer
# (SS-028+) actually reads a value, and main.py never imports this module.
app_config_service = AppConfigService(SupabaseAppConfigRepository())

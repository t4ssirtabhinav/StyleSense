"""Occasion slug normalisation for the backend (SS-025).

Implements steps 1-3 of the normalisation contract (design doc §3.6),
byte-identical to ``public.occasion_normalize_one`` in
``supabase/migrations/007_occasions_registry.sql`` and to
``normalizeOccasionSlug``/``resolveOccasionKey`` in
``mobile/features/onboarding/onboarding.occasions.ts``:

1. ``trim`` -> ``lower`` -> collapse runs of whitespace and ``-`` to a single
   ``_`` -> strip every character outside ``[a-z0-9_]``
2. if the result matches ``occasions.key``          -> use it
3. else if it matches ``occasion_aliases.alias``    -> use ``occasion_key``
4. else -> keep the normalised string and report it as unknown

Step 2 BEFORE step 3 is what makes an alias/key collision inert -- do not
reorder them.

Dedupe preserves FIRST-occurrence order and never sorts.

**Nothing here may ever raise.** A registry read failure falls back to the
last successful snapshot; with no snapshot at all it degrades to shape-only
normalisation. Tagging must never fail because the registry read failed, and
an unknown occasion must never be dropped or turned into an error -- it is a
signal about an occasion we haven't modelled yet.
"""

from __future__ import annotations

import logging
import re
import time

from adapters.interfaces import IOccasionRepository, OccasionRegistrySnapshot

logger = logging.getLogger(__name__)

_WHITESPACE_OR_DASH = re.compile(r"[\s-]+")
_NOT_SLUG_SAFE = re.compile(r"[^a-z0-9_]")

DEFAULT_REGISTRY_TTL_SECONDS = 60.0


def normalize_occasion_shape(raw: str) -> str:
    """Step 1 only. Returns ``""`` for an input that normalises to nothing
    (empty/whitespace/all-punctuation); callers treat that as "drop"."""
    collapsed = _WHITESPACE_OR_DASH.sub("_", raw.strip().lower())
    return _NOT_SLUG_SAFE.sub("", collapsed)


class OccasionNormalizer:
    """Holds an ``OccasionRegistrySnapshot`` behind a short in-process TTL
    cache, so a batch of items tagged back-to-back does not re-read the
    registry per item, while a newly-INSERTed occasion still reaches the
    Gemini prompt within a minute WITHOUT a redeploy (that "no rebuild"
    property is the ticket's headline AC)."""

    def __init__(
        self,
        repository: IOccasionRepository,
        *,
        ttl_seconds: float = DEFAULT_REGISTRY_TTL_SECONDS,
    ) -> None:
        self._repository = repository
        self._ttl_seconds = ttl_seconds
        self._snapshot: OccasionRegistrySnapshot | None = None
        self._fetched_at: float | None = None

    async def get_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        """Never raises. Returns the cached snapshot while fresh; otherwise
        refetches, and on failure falls back to the last successful snapshot
        (or an empty one if there has never been a successful read)."""
        now = time.monotonic()
        if (
            self._snapshot is not None
            and self._fetched_at is not None
            and (now - self._fetched_at) < self._ttl_seconds
        ):
            return self._snapshot

        try:
            snapshot = await self._repository.fetch_registry(jwt=jwt)
        except Exception as exc:  # noqa: BLE001 - registry read must never break tagging
            logger.warning("occasion_registry_fetch_failed", extra={"error": str(exc)})
            # Stale-but-serving beats empty. If there is no prior snapshot,
            # the empty one degrades to shape-only normalisation, which the
            # DB trigger then completes on write.
            return self._snapshot if self._snapshot is not None else OccasionRegistrySnapshot()

        self._snapshot = snapshot
        self._fetched_at = now
        return snapshot

    def resolve(self, raw: str, snapshot: OccasionRegistrySnapshot) -> str:
        """Steps 1-3 against an already-fetched snapshot. Returns ``""`` when
        the input normalises to nothing."""
        shaped = normalize_occasion_shape(raw)
        if not shaped:
            return ""
        # Canonical key wins BEFORE the alias lookup (collision-inert).
        if shaped in snapshot.keys:
            return shaped
        return snapshot.aliases.get(shaped, shaped)

    def normalize_with_snapshot(
        self, raw: list[str] | None, snapshot: OccasionRegistrySnapshot
    ) -> tuple[list[str], list[str]]:
        """Pure, I/O-free. Returns ``(normalized, unknown)``.

        ``unknown`` is a SUBSET of ``normalized`` -- unknown slugs are still
        written to the column; the caller logs them. ``None`` in, ``([], [])``
        out; no exception on any input.
        """
        if not raw:
            return [], []

        normalized: list[str] = []
        unknown: list[str] = []
        known = set(snapshot.keys)

        for entry in raw:
            if not isinstance(entry, str):
                continue
            resolved = self.resolve(entry, snapshot)
            if not resolved or resolved in normalized:
                continue
            normalized.append(resolved)
            if resolved not in known:
                unknown.append(resolved)

        return normalized, unknown

    async def normalize(self, raw: list[str] | None, *, jwt: str) -> tuple[list[str], list[str]]:
        """Fetch (or reuse) the registry, then normalise. Never raises."""
        snapshot = await self.get_registry(jwt=jwt)
        return self.normalize_with_snapshot(raw, snapshot)

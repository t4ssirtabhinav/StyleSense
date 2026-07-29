"""Tests for backend/services/occasion_normalizer.py (SS-025).

The normalisation contract (design doc §3.6) is implemented THREE times --
here, in `public.occasion_normalize_one` (007_occasions_registry.sql), and in
`mobile/features/onboarding/onboarding.occasions.ts`. The same table of cases
is asserted in the mobile suite (`onboarding.occasions.test.ts`) so the three
cannot drift silently.
"""

from __future__ import annotations

import pytest

from adapters.interfaces import IOccasionRepository, OccasionRegistrySnapshot
from services.occasion_normalizer import OccasionNormalizer, normalize_occasion_shape

REGISTRY_KEYS = (
    "office",
    "casual",
    "date_night",
    "wedding_guest",
    "festival",
    "puja",
    "party",
    "travel",
    "workout",
    "beach",
    "formal_event",
    "college",
)

ALIASES = {
    "wedding": "wedding_guest",
    "date": "date_night",
    "work": "office",
    "gym": "workout",
    "pooja": "puja",
    "vacation": "travel",
    "formal": "formal_event",
    "everyday": "casual",
}


class _FakeRepository(IOccasionRepository):
    def __init__(
        self,
        snapshot: OccasionRegistrySnapshot | None = None,
        *,
        fail_after: int | None = None,
    ) -> None:
        self.calls = 0
        self._snapshot = snapshot or OccasionRegistrySnapshot(
            keys=REGISTRY_KEYS, aliases=dict(ALIASES)
        )
        self._fail_after = fail_after

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        self.calls += 1
        if self._fail_after is not None and self.calls > self._fail_after:
            raise RuntimeError("registry read failed")
        return self._snapshot


def _snapshot() -> OccasionRegistrySnapshot:
    return OccasionRegistrySnapshot(keys=REGISTRY_KEYS, aliases=dict(ALIASES))


def _normalizer(repository: IOccasionRepository | None = None) -> OccasionNormalizer:
    return OccasionNormalizer(repository or _FakeRepository())


# --- step 1: shape ---------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("casual", "casual"),
        ("  Wedding Guest ", "wedding_guest"),
        ("Wedding Guest!!", "wedding_guest"),
        ("Ganesh-Chaturthi", "ganesh_chaturthi"),
        ("date   night", "date_night"),
        ("DATE_NIGHT", "date_night"),
        ("", ""),
        ("   ", ""),
        ("!!!", ""),
    ],
)
def test_normalize_occasion_shape_matches_the_contract(raw: str, expected: str) -> None:
    assert normalize_occasion_shape(raw) == expected


# --- steps 2-3: registry / alias resolution --------------------------------


def test_canonical_key_passes_through_unchanged() -> None:
    normalizer = _normalizer()
    assert normalizer.resolve("wedding_guest", _snapshot()) == "wedding_guest"
    assert normalizer.resolve("casual", _snapshot()) == "casual"


def test_aliases_map_to_their_canonical_keys() -> None:
    normalizer = _normalizer()
    assert normalizer.resolve("wedding", _snapshot()) == "wedding_guest"
    assert normalizer.resolve("date", _snapshot()) == "date_night"
    assert normalizer.resolve("pooja", _snapshot()) == "puja"


def test_messy_input_normalises_before_alias_lookup() -> None:
    normalizer = _normalizer()
    assert normalizer.resolve("  Wedding ", _snapshot()) == "wedding_guest"
    assert normalizer.resolve("Wedding Guest!!", _snapshot()) == "wedding_guest"


def test_key_alias_collision_resolves_to_the_canonical_key() -> None:
    """Resolution ORDER is the enforcement mechanism for key/alias
    disjointness -- there is no cross-table constraint and deliberately no
    trigger. If a row ever collides, the canonical key must win, making the
    collision inert."""
    colliding = OccasionRegistrySnapshot(
        keys=REGISTRY_KEYS,
        aliases={**ALIASES, "festival": "party"},
    )
    assert _normalizer().resolve("festival", colliding) == "festival"


# --- step 4: unknown capture ----------------------------------------------


def test_unknown_slug_is_kept_in_the_output_and_reported_as_unknown() -> None:
    normalized, unknown = _normalizer().normalize_with_snapshot(
        ["festival", "Ganesh Chaturthi"], _snapshot()
    )
    assert normalized == ["festival", "ganesh_chaturthi"]
    assert unknown == ["ganesh_chaturthi"]


def test_unknown_slugs_are_never_dropped_even_if_every_tag_is_unknown() -> None:
    normalized, unknown = _normalizer().normalize_with_snapshot(["sangeet", "mehendi"], _snapshot())
    assert normalized == ["sangeet", "mehendi"]
    assert unknown == ["sangeet", "mehendi"]


# --- dedupe + ordering -----------------------------------------------------


def test_duplicates_dedupe_preserving_first_occurrence_order() -> None:
    normalized, _ = _normalizer().normalize_with_snapshot(
        ["travel", "wedding", "Travel", "wedding_guest", "casual"], _snapshot()
    )
    assert normalized == ["travel", "wedding_guest", "casual"]


def test_output_is_never_sorted() -> None:
    normalized, _ = _normalizer().normalize_with_snapshot(["puja", "casual", "office"], _snapshot())
    assert normalized == ["puja", "casual", "office"]


# --- empty / None ----------------------------------------------------------


def test_empty_list_and_none_return_empty_without_raising() -> None:
    normalizer = _normalizer()
    assert normalizer.normalize_with_snapshot([], _snapshot()) == ([], [])
    assert normalizer.normalize_with_snapshot(None, _snapshot()) == ([], [])


def test_entries_that_normalise_to_nothing_are_dropped() -> None:
    normalized, unknown = _normalizer().normalize_with_snapshot(
        ["", "   ", "!!!", "casual"], _snapshot()
    )
    assert normalized == ["casual"]
    assert unknown == []


# --- registry fetch, caching and failure fallback --------------------------


async def test_registry_is_cached_for_the_ttl() -> None:
    repository = _FakeRepository()
    normalizer = OccasionNormalizer(repository, ttl_seconds=60.0)

    await normalizer.get_registry(jwt="jwt")
    await normalizer.get_registry(jwt="jwt")

    assert repository.calls == 1


async def test_expired_ttl_refetches() -> None:
    repository = _FakeRepository()
    normalizer = OccasionNormalizer(repository, ttl_seconds=0.0)

    await normalizer.get_registry(jwt="jwt")
    await normalizer.get_registry(jwt="jwt")

    assert repository.calls == 2


async def test_fetch_failure_falls_back_to_the_last_successful_snapshot() -> None:
    repository = _FakeRepository(fail_after=1)
    normalizer = OccasionNormalizer(repository, ttl_seconds=0.0)

    first = await normalizer.get_registry(jwt="jwt")
    second = await normalizer.get_registry(jwt="jwt")

    assert first.keys == REGISTRY_KEYS
    assert second.keys == REGISTRY_KEYS  # stale-but-serving, not empty
    assert repository.calls == 2


async def test_fetch_failure_with_no_prior_snapshot_degrades_without_raising() -> None:
    """Tagging must NEVER fail because the registry read failed. With no
    snapshot at all, normalisation degrades to shape-only -- the DB trigger
    completes the alias mapping on write."""
    repository = _FakeRepository(fail_after=0)
    normalizer = OccasionNormalizer(repository, ttl_seconds=0.0)

    normalized, unknown = await normalizer.normalize(["  Wedding Guest "], jwt="jwt")

    assert normalized == ["wedding_guest"]
    # Nothing is known when the registry is empty, so everything is reported
    # as unknown -- honest, and the caller only logs it.
    assert unknown == ["wedding_guest"]


async def test_normalize_end_to_end_maps_aliases_and_keeps_unknowns() -> None:
    normalized, unknown = await _normalizer().normalize(
        ["wedding", "date", "Ganesh Chaturthi", "wedding_guest"], jwt="jwt"
    )
    assert normalized == ["wedding_guest", "date_night", "ganesh_chaturthi"]
    assert unknown == ["ganesh_chaturthi"]

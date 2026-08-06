"""Tests for backend/services/garment_registry_adapter.py (SS-038)."""

from __future__ import annotations

from adapters.interfaces import GarmentRegistrySnapshot, GarmentTypeRow, IGarmentRegistryRepository
from services.garment_registry_adapter import GarmentRegistryAdapter


class _FakeRepository(IGarmentRegistryRepository):
    def __init__(self, snapshot: GarmentRegistrySnapshot | None = None, *, fail_after: int | None = None) -> None:
        self.calls = 0
        self._snapshot = snapshot or _default_snapshot()
        self._fail_after = fail_after

    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        self.calls += 1
        if self._fail_after is not None and self.calls > self._fail_after:
            raise RuntimeError("registry read failed")
        return self._snapshot


def _row(key: str, *, slot: str = "torso_base") -> GarmentTypeRow:
    return GarmentTypeRow(
        key=key,
        slot=slot,
        layer=0,
        register=("ethnic",),
        base_formality=4,
        pairs_with=(),
        requires_with=(),
        excludes_with=(),
        styling_rules={},
    )


def _default_snapshot() -> GarmentRegistrySnapshot:
    return GarmentRegistrySnapshot(
        rows={"palazzo": _row("palazzo", slot="legs"), "kurta": _row("kurta")},
        aliases={"plazo": "palazzo"},
    )


async def test_get_garment_attributes_resolves_canonical_key_hit() -> None:
    adapter = GarmentRegistryAdapter(_FakeRepository())
    await adapter.refresh()
    attrs = adapter.get_garment_attributes("kurta")
    assert attrs is not None
    assert attrs.key == "kurta"
    assert attrs.assembly_slot == "top"


async def test_get_garment_attributes_resolves_alias_before_any_fallback() -> None:
    """Alias resolution happens BEFORE any fallback -- the AC's explicit
    edge case."""
    adapter = GarmentRegistryAdapter(_FakeRepository())
    await adapter.refresh()
    attrs = adapter.get_garment_attributes("plazo")
    assert attrs is not None
    assert attrs.key == "palazzo"
    assert attrs.assembly_slot == "bottom"


async def test_get_garment_attributes_normalizes_case_and_whitespace() -> None:
    adapter = GarmentRegistryAdapter(_FakeRepository())
    await adapter.refresh()
    attrs = adapter.get_garment_attributes("  KURTA ")
    assert attrs is not None
    assert attrs.key == "kurta"


async def test_get_garment_attributes_returns_none_for_unknown_category() -> None:
    adapter = GarmentRegistryAdapter(_FakeRepository())
    await adapter.refresh()
    assert adapter.get_garment_attributes("some_unknown_category") is None


async def test_get_garment_attributes_returns_none_when_never_refreshed() -> None:
    """A caller bug (refresh() never awaited before the first lookup) --
    _snapshot starts None, treated as empty, every lookup returns None
    (full fallback) -- safe, not a crash."""
    adapter = GarmentRegistryAdapter(_FakeRepository())
    assert adapter.get_garment_attributes("kurta") is None


async def test_refresh_is_cached_for_the_ttl() -> None:
    repo = _FakeRepository()
    adapter = GarmentRegistryAdapter(repo, ttl_seconds=300.0)
    await adapter.refresh()
    await adapter.refresh()
    await adapter.refresh()
    assert repo.calls == 1


async def test_refresh_expired_ttl_refetches() -> None:
    repo = _FakeRepository()
    adapter = GarmentRegistryAdapter(repo, ttl_seconds=-1.0)  # always expired
    await adapter.refresh()
    await adapter.refresh()
    assert repo.calls == 2


async def test_refresh_failure_falls_back_to_last_good_snapshot() -> None:
    repo = _FakeRepository(fail_after=1)
    adapter = GarmentRegistryAdapter(repo, ttl_seconds=-1.0)  # always expired -> always refetches
    await adapter.refresh()  # succeeds, call 1
    await adapter.refresh()  # fails, call 2 -- degrades to last-good
    attrs = adapter.get_garment_attributes("kurta")
    assert attrs is not None  # last-good snapshot still served


async def test_refresh_failure_with_no_prior_snapshot_degrades_to_empty_without_raising() -> None:
    repo = _FakeRepository(fail_after=0)
    adapter = GarmentRegistryAdapter(repo)
    await adapter.refresh()  # must not raise
    assert adapter.get_garment_attributes("kurta") is None

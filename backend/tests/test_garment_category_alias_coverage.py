"""SS-044 -- fixture-level guards that CI can enforce for migration
022_garment_category_resolution.sql (design's "Test plan" T1-T6).

Fixture-level, not a live-DB test: builds a GarmentRegistrySnapshot that
mirrors what 022 actually inserts (the 13 NEW bucket rows aliased directly
by the enum, plus the pre-existing 014 rows that 6 of the 21 aliases point
at), then drives the SAME GarmentRegistryAdapter production code
(services/garment_registry_adapter.py) real consumers use. The live
verification bar -- "does the REAL linked project resolve every REAL
live category value" -- is backend/scripts/ss044_verify_category_resolution.py,
not this module (design's own "a passing unit test proves nothing new here"
instruction, carried over from SS-038's ticket text).
"""

from __future__ import annotations

from typing import get_args

from adapters.interfaces import GarmentRegistrySnapshot, GarmentTypeRow, IGarmentRegistryRepository
from ai.ports.interfaces import WardrobeCategory
from services.garment_registry_adapter import GarmentRegistryAdapter

# Transcribed verbatim from docs/tickets/SS-044-design.md section 1's table
# -- the single source of truth this test compares 022's actual seed
# against. A future enum value added without a matching alias row fails T1
# below rather than silently degrading.
EXPECTED_ALIAS_TO_KEY: dict[str, str] = {
    "western_top": "modern_top",
    "western_bottom": "modern_bottom",
    "western_dress": "dress",
    "western_outerwear": "modern_outerwear",
    "ethnic_kurta": "kurta",
    "ethnic_saree": "saree",
    "ethnic_lehenga": "lehenga_choli_set",
    "ethnic_anarkali": "anarkali",
    "ethnic_salwar_kameez": "salwar_kameez_set",
    "ethnic_dupatta": "dupatta",
    "ethnic_sherwani": "sherwani",
    "indo_western": "indo_western_outfit",
    "footwear_formal": "formal_footwear",
    "footwear_casual": "casual_footwear",
    "footwear_ethnic": "ethnic_footwear",
    "footwear_sports": "sports_footwear",
    "accessory_bag": "bag",
    "accessory_jewellery": "jewellery",
    "accessory_watch": "watch",
    "accessory_belt": "belt",
    "accessory_scarf": "scarf",
}

# Expected assembly_slot per design T3's explicit call-outs plus
# GARMENT_SLOT_TO_ASSEMBLY_SLOT's mapping (styling_rules_defaults.py).
EXPECTED_ASSEMBLY_SLOT: dict[str, str] = {
    "western_top": "top",
    "western_bottom": "bottom",
    "western_dress": "one_piece",
    "western_outerwear": "outerwear",
    "ethnic_kurta": "top",
    "ethnic_saree": "one_piece",
    "ethnic_lehenga": "one_piece",
    "ethnic_anarkali": "top",
    "ethnic_salwar_kameez": "one_piece",
    "ethnic_dupatta": "accessory",
    "ethnic_sherwani": "one_piece",
    "indo_western": "one_piece",
    "footwear_formal": "footwear",
    "footwear_casual": "footwear",
    "footwear_ethnic": "footwear",
    "footwear_sports": "footwear",
    "accessory_bag": "accessory",
    "accessory_jewellery": "accessory",
    "accessory_watch": "accessory",
    "accessory_belt": "accessory",
    "accessory_scarf": "accessory",
}


def _row(
    key: str,
    *,
    parent_key: str | None = None,
    slot: str,
    layer: int = 0,
    register: tuple[str, ...] = ("ethnic",),
    base_formality: int = 4,
    volume_class: str | None = "relaxed",
) -> GarmentTypeRow:
    return GarmentTypeRow(
        key=key,
        slot=slot,
        layer=layer,
        register=register,
        base_formality=base_formality,
        pairs_with=(),
        requires_with=(),
        excludes_with=(),
        styling_rules={"volume_class": volume_class} if volume_class else {},
    )


# The 13 NEW bucket rows 022 inserts (part 1a) -- transcribed from the
# migration/design table.
_NEW_ROWS: dict[str, GarmentTypeRow] = {
    "modern_top": _row(
        "modern_top",
        slot="torso_base",
        register=("western", "athleisure", "streetwear"),
        base_formality=2,
        volume_class="fitted",
    ),
    "dress": _row(
        "dress",
        parent_key="full_body_garment",
        slot="full_body",
        register=("western", "resort"),
        base_formality=5,
        volume_class="relaxed",
    ),
    "modern_outerwear": _row(
        "modern_outerwear",
        slot="torso_mid",
        layer=2,
        register=("western", "streetwear"),
        base_formality=4,
        volume_class="relaxed",
    ),
    "indo_western_outfit": _row(
        "indo_western_outfit",
        parent_key="full_body_garment",
        slot="full_body",
        register=("indo_western",),
        base_formality=5,
        volume_class="relaxed",
    ),
    "formal_footwear": _row(
        "formal_footwear",
        slot="feet",
        register=("western", "indo_western"),
        base_formality=7,
        volume_class="fitted",
    ),
    "casual_footwear": _row(
        "casual_footwear",
        slot="feet",
        register=("western", "athleisure", "streetwear"),
        base_formality=3,
        volume_class="fitted",
    ),
    "ethnic_footwear": _row(
        "ethnic_footwear",
        slot="feet",
        register=("ethnic", "indo_western"),
        base_formality=6,
        volume_class="fitted",
    ),
    "sports_footwear": _row(
        "sports_footwear",
        slot="feet",
        register=("athleisure", "streetwear"),
        base_formality=1,
        volume_class="fitted",
    ),
    "bag": _row(
        "bag",
        slot="carry",
        register=("western", "ethnic", "indo_western", "streetwear"),
        base_formality=4,
        volume_class="fitted",
    ),
    "jewellery": _row(
        "jewellery",
        slot="neck",
        register=("ethnic", "indo_western", "western"),
        base_formality=5,
        volume_class="fitted",
    ),
    "watch": _row(
        "watch",
        slot="wrist",
        register=("western", "indo_western", "athleisure"),
        base_formality=4,
        volume_class="fitted",
    ),
    "belt": _row(
        "belt",
        slot="waist",
        register=("western", "indo_western", "streetwear"),
        base_formality=3,
        volume_class="fitted",
    ),
    "scarf": _row(
        "scarf",
        slot="drape",
        layer=2,
        register=("western", "indo_western"),
        base_formality=3,
        volume_class="relaxed",
    ),
}

# The pre-existing 014 rows that 8 of the 21 aliases resolve onto
# (western_bottom -> modern_bottom, a 014 PARENT row, plus the 7 ethnic
# rows below -- these are NOT touched by 022's INSERT, only by its
# volume_class backfill, so their fixture volume_class values below are
# the POST-022 (backfilled) state, not 014's pre-migration '{}').
_EXISTING_014_ROWS: dict[str, GarmentTypeRow] = {
    "modern_bottom": _row(
        "modern_bottom",
        slot="legs",
        register=("western", "athleisure", "streetwear"),
        base_formality=2,
        volume_class="relaxed",
    ),
    "kurta": _row(
        "kurta",
        parent_key="ethnic_top",
        slot="torso_base",
        register=("ethnic", "indo_western"),
        base_formality=4,
        volume_class="relaxed",
    ),
    "saree": _row(
        "saree", slot="full_body", register=("ethnic",), base_formality=7, volume_class="relaxed"
    ),
    "lehenga_choli_set": _row(
        "lehenga_choli_set",
        parent_key="garment_set",
        slot="set",
        register=("ethnic",),
        base_formality=9,
        volume_class="voluminous",
    ),
    "anarkali": _row(
        "anarkali",
        parent_key="ethnic_top",
        slot="torso_base",
        register=("ethnic",),
        base_formality=7,
        volume_class="voluminous",
    ),
    "salwar_kameez_set": _row(
        "salwar_kameez_set",
        parent_key="garment_set",
        slot="set",
        register=("ethnic",),
        base_formality=5,
        volume_class="relaxed",
    ),
    "dupatta": _row(
        "dupatta",
        parent_key="drape",
        slot="drape",
        layer=2,
        register=("ethnic",),
        base_formality=5,
        volume_class="relaxed",
    ),
    "sherwani": _row(
        "sherwani",
        parent_key="full_body_garment",
        slot="full_body",
        layer=2,
        register=("ethnic",),
        base_formality=8,
        volume_class="relaxed",
    ),
}

_ALL_ROWS: dict[str, GarmentTypeRow] = {**_NEW_ROWS, **_EXISTING_014_ROWS}


def _fixture_snapshot(*, extra_aliases: dict[str, str] | None = None) -> GarmentRegistrySnapshot:
    aliases = dict(EXPECTED_ALIAS_TO_KEY)
    if extra_aliases:
        aliases.update(extra_aliases)
    return GarmentRegistrySnapshot(rows=dict(_ALL_ROWS), aliases=aliases)


class _FakeRepository(IGarmentRegistryRepository):
    def __init__(self, snapshot: GarmentRegistrySnapshot) -> None:
        self._snapshot = snapshot

    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        return self._snapshot


async def _adapter_for(snapshot: GarmentRegistrySnapshot) -> GarmentRegistryAdapter:
    adapter = GarmentRegistryAdapter(_FakeRepository(snapshot))
    await adapter.refresh()
    return adapter


# ---------------------------------------------------------------------------
# T1 -- every WardrobeCategory member has an alias row naming an existing key
# ---------------------------------------------------------------------------


def test_t1_every_wardrobe_category_has_an_alias_to_an_existing_key() -> None:
    categories = set(get_args(WardrobeCategory))
    assert categories == set(EXPECTED_ALIAS_TO_KEY), (
        "EXPECTED_ALIAS_TO_KEY (transcribed from the design doc) must cover every "
        "WardrobeCategory member exactly -- a future enum value added without an "
        "alias must fail here, not silently degrade"
    )
    for category, garment_key in EXPECTED_ALIAS_TO_KEY.items():
        assert garment_key in _ALL_ROWS, (
            f"{category} -> {garment_key}, but {garment_key} is not a known garment_types row"
        )


# ---------------------------------------------------------------------------
# T2 -- alias/key disjointness, extended to the 21 new rows
# ---------------------------------------------------------------------------


def test_t2_aliases_and_keys_are_disjoint() -> None:
    assert set(EXPECTED_ALIAS_TO_KEY) & set(_ALL_ROWS) == set(), (
        "no live wardrobe_category value may ever equal an existing garment_types.key "
        "(would make the alias row inert, masked by canonical-key-first resolution order)"
    )


# ---------------------------------------------------------------------------
# T3 -- every value resolves, with the correct assembly_slot
# ---------------------------------------------------------------------------


async def test_t3_every_category_resolves_to_the_correct_assembly_slot() -> None:
    adapter = await _adapter_for(_fixture_snapshot())
    for category in get_args(WardrobeCategory):
        attrs = adapter.get_garment_attributes(category)
        assert attrs is not None, f"{category} did not resolve (BL-156 regression)"
        assert attrs.assembly_slot in {
            "top",
            "bottom",
            "one_piece",
            "outerwear",
            "footwear",
            "accessory",
        }
        assert attrs.assembly_slot == EXPECTED_ASSEMBLY_SLOT[category], (
            f"{category} resolved to assembly_slot={attrs.assembly_slot!r}, "
            f"expected {EXPECTED_ASSEMBLY_SLOT[category]!r}"
        )

    footwear_categories = [
        "footwear_formal",
        "footwear_casual",
        "footwear_ethnic",
        "footwear_sports",
    ]
    for category in footwear_categories:
        assert adapter.get_garment_attributes(category).assembly_slot == "footwear"  # type: ignore[union-attr]

    assert adapter.get_garment_attributes("accessory_bag").assembly_slot == "accessory"  # type: ignore[union-attr]
    assert adapter.get_garment_attributes("accessory_watch").assembly_slot == "accessory"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# T4 -- every value resolves with a populated volume_class (BL-191 guard)
# ---------------------------------------------------------------------------


async def test_t4_every_category_resolves_with_a_populated_volume_class() -> None:
    adapter = await _adapter_for(_fixture_snapshot())
    for category in get_args(WardrobeCategory):
        attrs = adapter.get_garment_attributes(category)
        assert attrs is not None
        assert attrs.volume_class is not None, (
            f"{category} resolved but volume_class is unset -- BL-191 regression, "
            "volume_balance_score would go silently inert again for this category"
        )
        assert attrs.volume_class in {"fitted", "relaxed", "voluminous"}


# ---------------------------------------------------------------------------
# T5 -- parity between the design's transcribed table and what actually
# ships (022's real INSERT ... VALUES statement below), so a hand-edit to
# either one drifting from the other fails loudly.
# ---------------------------------------------------------------------------


def test_t5_migration_file_alias_seed_matches_the_transcribed_expectation_table() -> None:
    from pathlib import Path

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "022_garment_category_resolution.sql"
    )
    assert migration_path.is_file(), f"expected migration file at {migration_path}"
    sql = migration_path.read_text(encoding="utf-8")

    # Extract the literal ('alias', 'garment_key') pairs from the
    # `INSERT INTO garment_type_aliases` VALUES block -- a lightweight,
    # deliberately narrow parse (not a general SQL parser) matching exactly
    # this migration's own uniform ('x', 'y') tuple shape.
    import re

    pairs = re.findall(r"\('([a-z_]+)',\s*'([a-z_]+)'\)", sql)
    # The migration also seeds garment_types rows with parenthesised tuples
    # that match this same shallow shape incidentally (e.g. none do, since
    # those rows are 7+ columns) -- restrict to pairs whose first element is
    # a real WardrobeCategory member, which the alias tuples are and the
    # garment_types tuples never are.
    categories = set(get_args(WardrobeCategory))
    found_alias_to_key = {alias: key for alias, key in pairs if alias in categories}

    assert found_alias_to_key == EXPECTED_ALIAS_TO_KEY, (
        "022_garment_category_resolution.sql's actual alias seed diverged from the "
        f"design's transcribed expectation table: {found_alias_to_key} != {EXPECTED_ALIAS_TO_KEY}"
    )


async def test_t5_adapter_resolution_matches_the_expectation_table() -> None:
    """The other half of parity (edge case 10): the Python adapter's
    resolved key equals the design's transcribed expectation for every one
    of the 21 values."""
    adapter = await _adapter_for(_fixture_snapshot())
    for category, expected_key in EXPECTED_ALIAS_TO_KEY.items():
        attrs = adapter.get_garment_attributes(category)
        assert attrs is not None
        assert attrs.key == expected_key


# ---------------------------------------------------------------------------
# T6 -- canonical-key-first resolution order (edge case 3)
# ---------------------------------------------------------------------------


async def test_t6_canonical_key_wins_over_a_colliding_alias() -> None:
    """A fixture alias deliberately colliding with a real key -- resolution
    must prefer the key, never the alias target, mirroring
    garment_normalize_one's step-2-before-step-3 order."""
    snapshot = _fixture_snapshot(extra_aliases={"kurta": "saree"})
    adapter = await _adapter_for(snapshot)
    attrs = adapter.get_garment_attributes("kurta")
    assert attrs is not None
    assert attrs.key == "kurta", (
        "canonical key must win over a colliding alias, never the alias target"
    )

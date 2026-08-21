"""Tests for backend/services/rail_precompute_service.py (SS-048), against
fake repos/adapters -- no real network/DB calls, no real Engine v2 pipeline
(a fake engine returns a canned ``EngineV2Result`` so slicing/payload
behaviour is asserted deterministically, independent of real scoring)."""

from __future__ import annotations

from typing import Any

from adapters.interfaces import (
    GarmentRegistrySnapshot,
    IGarmentRegistryRepository,
    IOccasionRepository,
    IOutfitRepository,
    ISuggestionRailsRepository,
    IWardrobeRepository,
    OccasionRegistrySnapshot,
    OutfitInsert,
    SuggestionRailRow,
    SuggestionRailUpsert,
)
from services.engine_v2 import ENGINE_VERSION
from services.engine_v2_portfolio import compute_outfit_fingerprint
from services.engine_v2_types import EngineV2Result, PortfolioCandidate
from services.garment_registry_adapter import GarmentRegistryAdapter
from services.occasion_normalizer import OccasionNormalizer
from services.rail_precompute_service import RailPrecomputeService
from services.styling_rules_types import GapReport, ScoredCandidate

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(
        self,
        *,
        styling_rows: list[dict[str, Any]] | None = None,
        rail_rows: list[dict[str, Any]] | None = None,
        image_info: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._styling_rows = styling_rows if styling_rows is not None else []
        self._rail_rows = rail_rows if rail_rows is not None else []
        self._image_info = image_info if image_info is not None else {}

    async def upsert_uploaded_row(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def update_bg_removal_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_plan_tier(self, *, jwt: str, user_id: str) -> str:
        raise NotImplementedError

    async def item_exists(self, *, jwt: str, item_id: str) -> bool:
        raise NotImplementedError

    async def update_tagging_result(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_item_image_info(self, *, jwt: str, item_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    async def get_items_image_info_bulk(
        self, *, jwt: str, item_ids: list[str]
    ) -> dict[str, dict[str, Any]]:
        return {k: v for k, v in self._image_info.items() if k in item_ids}

    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        raise NotImplementedError

    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        return self._styling_rows

    async def get_items_for_rails(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        return self._rail_rows

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        return None

    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        raise NotImplementedError


class _FakeOutfitRepo(IOutfitRepository):
    def __init__(self, item_ids_rows: list[list[str]] | None = None) -> None:
        self._item_ids_rows = item_ids_rows if item_ids_rows is not None else []

    async def insert_outfit(self, *, jwt: str, outfit: OutfitInsert) -> tuple[str, bool]:
        raise NotImplementedError

    async def insert_wear_rows(self, **kwargs: Any) -> bool:
        raise NotImplementedError

    async def get_item_ids_for_user(self, *, jwt: str, user_id: str) -> list[list[str]]:
        return self._item_ids_rows


class _FakeGarmentRegistryRepo(IGarmentRegistryRepository):
    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        return GarmentRegistrySnapshot(rows={}, aliases={})


class _FakeOccasionRepo(IOccasionRepository):
    def __init__(self, snapshot: OccasionRegistrySnapshot) -> None:
        self._snapshot = snapshot

    async def fetch_registry(self, *, jwt: str) -> OccasionRegistrySnapshot:
        return self._snapshot


class _FakeRailsRepo(ISuggestionRailsRepository):
    def __init__(self) -> None:
        self.upsert_calls: list[list[SuggestionRailUpsert]] = []

    async def upsert_rails(
        self, *, jwt: str, user_id: str, rails: list[SuggestionRailUpsert]
    ) -> None:
        self.upsert_calls.append(rails)

    async def get_rails(self, *, jwt: str, user_id: str) -> list[SuggestionRailRow]:
        raise NotImplementedError

    async def get_most_recent_computed_at(self, *, jwt: str, user_id: str) -> Any:
        raise NotImplementedError


class _FakeEngine:
    """Duck-typed against ``EngineV2``'s own public shape -- returns a
    canned ``EngineV2Result`` so slicing/payload behaviour is asserted
    deterministically, independent of real Engine v2 scoring."""

    def __init__(self, result: EngineV2Result) -> None:
        self._result = result
        self.call_count = 0

    async def generate_portfolio(self, *args: Any, **kwargs: Any) -> EngineV2Result:
        self.call_count += 1
        return self._result


def _candidate(item_ids: list[str], *, total_score: float) -> PortfolioCandidate:
    return PortfolioCandidate(
        candidate=ScoredCandidate(
            item_ids=item_ids,
            category_labels={},
            total_score=total_score,
            rule_scores=[],
            gap_flags=[],
        ),
        is_exploration=False,
    )


def _engine_result(portfolio: list[PortfolioCandidate]) -> EngineV2Result:
    return EngineV2Result(
        portfolio=portfolio,
        limited_options=False,
        gap_report=GapReport(),
        session_id="session-1",
        engine_version=ENGINE_VERSION,
    )


def _occasion_snapshot() -> OccasionRegistrySnapshot:
    return OccasionRegistrySnapshot(
        keys=("everyday",),
        aliases={},
        labels={"everyday": "Everyday"},
        badge_colors={"everyday": "everyday"},
        kinds={"everyday": "everyday"},
        formalities={"everyday": 3},
        styling_rules={"everyday": {}},
    )


def _rail_row(
    item_id: str, *, created_at: str, wear_count: int = 0, category: str = "ethnic_kurta"
) -> dict[str, Any]:
    return {
        "id": item_id,
        "category": category,
        "color_primary": "#000000",
        "created_at": created_at,
        "wear_count": wear_count,
        "do_not_style": False,
        "is_archived": False,
    }


def _build_service(
    *,
    engine: _FakeEngine,
    wardrobe_repo: _FakeWardrobeRepo,
    outfit_repo: _FakeOutfitRepo | None = None,
    rails_repo: _FakeRailsRepo | None = None,
) -> tuple[RailPrecomputeService, _FakeRailsRepo]:
    rails_repo = rails_repo or _FakeRailsRepo()
    service = RailPrecomputeService(
        engine=engine,  # type: ignore[arg-type]
        wardrobe_repo=wardrobe_repo,
        outfit_repo=outfit_repo or _FakeOutfitRepo(),
        garment_registry=GarmentRegistryAdapter(_FakeGarmentRegistryRepo()),
        rails_repo=rails_repo,
        occasion_normalizer=OccasionNormalizer(_FakeOccasionRepo(_occasion_snapshot())),
    )
    return service, rails_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_generate_portfolio_called_exactly_once_per_invocation() -> None:
    engine = _FakeEngine(_engine_result([_candidate(["a", "b"], total_score=0.9)]))
    service, _ = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    assert engine.call_count == 1


async def test_todays_picks_is_top_5_in_engine_ranked_order() -> None:
    candidates = [_candidate([f"item-{i}"], total_score=1.0 - i * 0.01) for i in range(8)]
    engine = _FakeEngine(_engine_result(candidates))
    service, rails_repo = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    todays_picks = next(r for r in rails_repo.upsert_calls[0] if r.rail_key == "todays_picks")
    items = todays_picks.payload["items"]
    assert len(items) == 5
    assert [item["item_ids"] for item in items] == [[f"item-{i}"] for i in range(5)]


async def test_newest_pieces_only_includes_candidates_intersecting_anchor_set() -> None:
    # Anchor set = top 5 by created_at desc -> "new-0".."new-4". "old-item" is
    # NOT in the anchor set (oldest), so a candidate built only from it must
    # be excluded even though it's a valid engine candidate.
    rail_rows = [_rail_row(f"new-{i}", created_at=f"2026-08-{10 + i:02d}") for i in range(5)]
    rail_rows.append(_rail_row("old-item", created_at="2026-01-01"))

    candidates = [
        _candidate(["new-0"], total_score=0.5),
        _candidate(["old-item"], total_score=0.99),  # highest score, but anchor-ineligible
    ]
    engine = _FakeEngine(_engine_result(candidates))
    service, rails_repo = _build_service(
        engine=engine, wardrobe_repo=_FakeWardrobeRepo(rail_rows=rail_rows)
    )

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    newest_pieces = next(r for r in rails_repo.upsert_calls[0] if r.rail_key == "newest_pieces")
    items = newest_pieces.payload["items"]
    assert len(items) == 1
    assert items[0]["item_ids"] == ["new-0"]


async def test_newest_pieces_empty_when_no_candidate_intersects_anchor_set() -> None:
    rail_rows = [_rail_row("new-0", created_at="2026-08-10")]
    candidates = [_candidate(["unrelated-item"], total_score=0.9)]
    engine = _FakeEngine(_engine_result(candidates))
    service, rails_repo = _build_service(
        engine=engine, wardrobe_repo=_FakeWardrobeRepo(rail_rows=rail_rows)
    )

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    newest_pieces = next(r for r in rails_repo.upsert_calls[0] if r.rail_key == "newest_pieces")
    assert newest_pieces.payload["items"] == []


async def test_engine_version_stamped_correctly_per_rail() -> None:
    engine = _FakeEngine(_engine_result([_candidate(["a"], total_score=0.5)]))
    service, rails_repo = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    by_key = {r.rail_key: r for r in rails_repo.upsert_calls[0]}
    assert by_key["todays_picks"].engine_version == ENGINE_VERSION
    assert by_key["newest_pieces"].engine_version == ENGINE_VERSION
    assert by_key["never_tried_pairs"].engine_version is None
    assert by_key["not_yet_worn"].engine_version is None


async def test_empty_wardrobe_produces_empty_payloads_for_all_four_rails_without_raising() -> None:
    engine = _FakeEngine(_engine_result([]))
    service, rails_repo = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    for rail in rails_repo.upsert_calls[0]:
        assert rail.payload["items"] == []


async def test_upsert_rails_called_once_per_recompute_with_all_four_rail_keys_each_time() -> None:
    engine = _FakeEngine(_engine_result([_candidate(["a"], total_score=0.5)]))
    service, rails_repo = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")
    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    assert len(rails_repo.upsert_calls) == 2
    for call in rails_repo.upsert_calls:
        assert {r.rail_key for r in call} == {
            "todays_picks",
            "newest_pieces",
            "never_tried_pairs",
            "not_yet_worn",
        }


async def test_stored_outfit_fingerprint_matches_engine_v2_portfolio_function_exactly() -> None:
    engine = _FakeEngine(_engine_result([_candidate(["a", "b"], total_score=0.5)]))
    service, rails_repo = _build_service(engine=engine, wardrobe_repo=_FakeWardrobeRepo())

    await service.recompute_all_rails(jwt="jwt", user_id="u1")

    todays_picks = next(r for r in rails_repo.upsert_calls[0] if r.rail_key == "todays_picks")
    item = todays_picks.payload["items"][0]
    assert item["outfit_fingerprint"] == compute_outfit_fingerprint(["a", "b"])

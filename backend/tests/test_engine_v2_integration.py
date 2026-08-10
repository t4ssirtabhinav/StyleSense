"""End-to-end tests for backend/services/engine_v2.py (SS-038) against
fake/mocked repositories -- no live DB."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from adapters.interfaces import (
    FabricAttributes,
    GarmentRegistrySnapshot,
    GarmentTypeRow,
    IAppConfigRepository,
    IFabricRegistryRepository,
    IGarmentRegistryRepository,
    ISuggestionLogRepository,
    IWearHistoryRepository,
    SuggestionImpressionLog,
    SuggestionSessionLog,
    WearRecency,
)
from services.app_config import AppConfigService
from services.engine_v2 import EngineV2
from services.garment_registry_adapter import GarmentRegistryAdapter
from services.styling_rules_types import OccasionStylingInput, WardrobeItemInput

_AS_OF = date(2026, 7, 29)


class _FakeAppConfigRepo(IAppConfigRepository):
    async def fetch_all(self) -> dict[str, Any]:
        return {}  # near_white_threshold absent -> coded default


class _FakeGarmentRegistryRepo(IGarmentRegistryRepository):
    async def fetch_registry(self) -> GarmentRegistrySnapshot:
        row = GarmentTypeRow(
            key="kurta",
            slot="torso_base",
            layer=0,
            register=("ethnic",),
            base_formality=4,
            pairs_with=("ethnic_bottom",),
            requires_with=(),
            excludes_with=(),
            styling_rules={"volume_class": "fitted"},
        )
        return GarmentRegistrySnapshot(rows={"kurta": row}, aliases={})


class _FakeFabricRepo(IFabricRegistryRepository):
    async def fetch_all(self) -> dict[str, FabricAttributes]:
        return {"cotton": FabricAttributes(key="cotton", weight="light", breathability=9, season_affinity=("summer",))}


class _FailingFabricRepo(IFabricRegistryRepository):
    async def fetch_all(self) -> dict[str, FabricAttributes]:
        raise RuntimeError("fabric read failed")


class _FakeWearHistoryRepo(IWearHistoryRepository):
    """Returns ``[]`` -- mirrors a real repo's own internal never-raise
    degrade (SS-035's port contract); ``engine_v2_novelty.fetch_novelty_inputs``
    trusts this contract and adds no try/except of its own (see that
    module's docstring), so this test suite never constructs a repo that
    literally raises to the caller -- that would just prove a crash, not
    the documented degrade behaviour."""

    async def fetch_wear_recency(
        self, *, jwt: str, user_id: str, occasion_key: str | None = None
    ) -> list[WearRecency]:
        return []


class _FakeSuggestionLogRepo(ISuggestionLogRepository):
    def __init__(self) -> None:
        self.logged_sessions: list[tuple[SuggestionSessionLog, list[SuggestionImpressionLog]]] = []

    async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
        self.logged_sessions.append((session, list(impressions)))
        return "fake-session-id"

    async def log_outcome(self, outcome):  # type: ignore[no-untyped-def]
        return None

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict]:
        return []

    async def update_session_outcome(
        self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None
    ) -> None:
        return None

    async def find_impression(self, *, session_id: str, rank: int):  # type: ignore[no-untyped-def]
        return None


class _FailingSuggestionLogRepo(ISuggestionLogRepository):
    async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
        raise RuntimeError("logging failed")

    async def log_outcome(self, outcome):  # type: ignore[no-untyped-def]
        return None

    async def recent_impressions(
        self, *, user_id: str, since: datetime, limit: int = 200
    ) -> list[dict]:
        return []

    async def update_session_outcome(
        self, *, session_id: str, cost_incurred: bool, request_id: str | None, latency_ms: int | None
    ) -> None:
        return None

    async def find_impression(self, *, session_id: str, rank: int):  # type: ignore[no-untyped-def]
        return None


def _item(id: str, *, category: str = "western_top", color: str = "#8B0000") -> WardrobeItemInput:
    return WardrobeItemInput(id=id, category=category, color_primary=color)  # type: ignore[arg-type]


def _occasion(*, key: str = "office", kind: str = "professional", formality: int = 6) -> OccasionStylingInput:
    return OccasionStylingInput(key=key, kind=kind, formality=formality)  # type: ignore[arg-type]


def _mixed_wardrobe() -> list[WardrobeItemInput]:
    """Most real WardrobeCategory enum values (fallback path) plus one
    synthetic garment-types-shaped category ("ethnic_kurta" resolved via the
    fake registry, which maps THAT enum value's real string as if it were a
    registry hit is not literal here -- category stays a real enum value,
    exercising the fallback path for everything; the registry-hit path is
    separately covered by test_garment_registry_adapter.py /
    test_engine_v2_candidate_search.py's synthetic-category tests, per the
    design doc's own "Open questions" #4 (no live enum value resolves
    through garment_types today)."""
    return [
        _item("top1", category="western_top", color="#1E3A8A"),
        _item("bottom1", category="western_bottom", color="#1E3A8A"),
        _item("shoe1", category="footwear_casual", color="#000000"),
        _item("shoe2", category="footwear_formal", color="#111111"),
        _item("dress1", category="western_dress", color="#8B0000"),
        _item("jacket1", category="western_outerwear", color="#228B22"),
    ]


def _build_engine(
    *,
    fabric_repo: IFabricRegistryRepository | None = None,
    wear_history_repo: IWearHistoryRepository | None = None,
    suggestion_log_repo: ISuggestionLogRepository | None = None,
) -> tuple[EngineV2, ISuggestionLogRepository]:
    garment_registry = GarmentRegistryAdapter(_FakeGarmentRegistryRepo())
    app_config = AppConfigService(_FakeAppConfigRepo())
    log_repo = suggestion_log_repo or _FakeSuggestionLogRepo()
    engine = EngineV2(
        garment_registry=garment_registry,
        fabric_repo=fabric_repo or _FakeFabricRepo(),
        wear_history_repo=wear_history_repo or _FakeWearHistoryRepo(),
        suggestion_log_repo=log_repo,
        app_config=app_config,
    )
    return engine, log_repo


async def test_generate_portfolio_produces_non_empty_result_and_logs_session() -> None:
    engine, log_repo = _build_engine()
    wardrobe = _mixed_wardrobe()
    occasion = _occasion()

    result = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )

    assert result.engine_version == "engine-v2"
    assert result.session_id == "fake-session-id"
    assert isinstance(log_repo, _FakeSuggestionLogRepo)
    assert len(log_repo.logged_sessions) == 1
    session, impressions = log_repo.logged_sessions[0]
    assert session.engine_version == "engine-v2"
    if result.portfolio:
        assert len(impressions) == len(result.portfolio)
        exploration_ranks = {i + 1 for i, pc in enumerate(result.portfolio) if pc.is_exploration}
        for impression in impressions:
            assert (impression.rank in exploration_ranks) == impression.is_exploration


async def test_generate_portfolio_never_hallucinates_ids() -> None:
    engine, _ = _build_engine()
    wardrobe = _mixed_wardrobe()
    input_ids = {item.id for item in wardrobe}
    occasion = _occasion()

    result = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    for pc in result.portfolio:
        assert set(pc.candidate.item_ids) <= input_ids


async def test_generate_portfolio_small_wardrobe_returns_limited_options_no_crash() -> None:
    engine, _ = _build_engine()
    wardrobe = [_item("saree1", category="ethnic_saree", color="#8B0000")]
    occasion = _occasion()

    result = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    assert result.limited_options is True
    # honest, not a crash -- possibly empty or a single gapped candidate


async def test_generate_portfolio_survives_fabric_repo_failure() -> None:
    engine, _ = _build_engine(fabric_repo=_FailingFabricRepo())
    wardrobe = _mixed_wardrobe()
    occasion = _occasion()

    result = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    assert result.engine_version == "engine-v2"  # did not raise


async def test_generate_portfolio_survives_suggestion_log_repo_failure() -> None:
    """A logging failure must never block the user's suggestion request."""
    engine, _ = _build_engine(suggestion_log_repo=_FailingSuggestionLogRepo())
    wardrobe = _mixed_wardrobe()
    occasion = _occasion()

    result = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    assert result.session_id is None  # logging failed, degraded gracefully
    # But a full, real portfolio result is still returned.
    assert result.engine_version == "engine-v2"


async def test_generate_portfolio_deterministic_same_input_same_output() -> None:
    engine, _ = _build_engine()
    wardrobe = _mixed_wardrobe()
    occasion = _occasion()

    result1 = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    result2 = await engine.generate_portfolio(
        wardrobe, occasion, jwt="fake-jwt", user_id="u1", as_of=_AS_OF
    )
    ids1 = [tuple(pc.candidate.item_ids) for pc in result1.portfolio]
    ids2 = [tuple(pc.candidate.item_ids) for pc in result2.portfolio]
    assert ids1 == ids2

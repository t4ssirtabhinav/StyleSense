"""Tests for backend/services/outfit_outcome_service.py (SS-023) --
docs/tickets/SS-023-design.md section 3/§6/§7's exact write path, against
fake repos. No real network/DB calls.

Test #2 (cross-tenant) is the single most important test in this ticket --
asserted on the fakes' call logs, not just the raised exception.
"""

from __future__ import annotations

from typing import Any

import pytest

from adapters.interfaces import (
    ImpressionRef,
    IOutfitRepository,
    ISuggestionLogRepository,
    IWardrobeRepository,
    OutfitInsert,
    SuggestionOutcomeLog,
)
from services.ist_window import ist_today
from services.outfit_outcome_service import OutcomeNotFoundError, OutfitOutcomeService

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeSuggestionLogRepo(ISuggestionLogRepository):
    def __init__(
        self,
        *,
        impression: ImpressionRef | None,
        log_outcome_result: str | None = "outcome-1",
    ) -> None:
        self._impression = impression
        self._log_outcome_result = log_outcome_result
        self.log_outcome_calls: list[SuggestionOutcomeLog] = []

    async def log_session(self, session, impressions):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def log_outcome(self, outcome: SuggestionOutcomeLog) -> str | None:
        self.log_outcome_calls.append(outcome)
        return self._log_outcome_result

    async def recent_impressions(self, *, user_id, since, limit=200):  # type: ignore[no-untyped-def]
        return []

    async def update_session_outcome(self, **kwargs: Any) -> None:
        return None

    async def find_impression(self, *, session_id: str, rank: int) -> ImpressionRef | None:
        return self._impression


class _FakeOutfitRepo(IOutfitRepository):
    def __init__(
        self,
        *,
        insert_result: tuple[str, bool] = ("outfit-1", False),
        insert_wear_result: bool = True,
    ) -> None:
        self._insert_result = insert_result
        self._insert_wear_result = insert_wear_result
        self.insert_outfit_calls: list[OutfitInsert] = []
        self.insert_wear_calls: list[dict[str, Any]] = []

    async def insert_outfit(self, *, jwt: str, outfit: OutfitInsert) -> tuple[str, bool]:
        self.insert_outfit_calls.append(outfit)
        return self._insert_result

    async def insert_wear_rows(
        self,
        *,
        jwt: str,
        user_id: str,
        item_ids: list[str],
        worn_on: str,
        occasion_key: str | None,
        outfit_id: str,
    ) -> bool:
        self.insert_wear_calls.append(
            {
                "user_id": user_id,
                "item_ids": item_ids,
                "worn_on": worn_on,
                "occasion_key": occasion_key,
                "outfit_id": outfit_id,
            }
        )
        return self._insert_wear_result

    # SS-048 mechanical addition: same ABC-extension trap noted above.
    async def get_item_ids_for_user(self, *, jwt: str, user_id: str) -> list[list[str]]:
        raise NotImplementedError


class _FakeWardrobeRepo(IWardrobeRepository):
    def __init__(
        self,
        *,
        styling_rows: list[dict[str, Any]] | None = None,
        image_info: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._styling_rows = styling_rows if styling_rows is not None else []
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

    async def get_items_image_info_bulk(self, **kwargs: Any) -> dict[str, dict[str, Any]]:
        return self._image_info

    async def delete_item(self, *, jwt: str, item_id: str) -> bool:
        raise NotImplementedError

    async def get_items_for_styling(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        return self._styling_rows

    # SS-048 mechanical addition: same ABC-extension trap as the SS-022 note
    # below -- IWardrobeRepository grew a new abstract method, every fake
    # implementing it must add a stub or the class can't be instantiated.
    async def get_items_for_rails(self, *, jwt: str, user_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def get_style_preferences(self, *, jwt: str, user_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    # SS-022 mechanical addition: same ABC-extension trap as above.
    async def get_city(self, *, jwt: str, user_id: str) -> str | None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _impression(
    *,
    user_id: str = "user-1",
    item_ids: list[str] | None = None,
    occasion: str | None = "office",
) -> ImpressionRef:
    return ImpressionRef(
        impression_id="impression-1",
        user_id=user_id,
        session_id="session-1",
        rank=1,
        item_ids=item_ids or ["item-a", "item-b"],
        outfit_fingerprint="a" * 64,
        total_score=0.85,
        is_exploration=False,
        occasion=occasion,
    )


def _service(
    *,
    impression: ImpressionRef | None,
    outfit_repo: _FakeOutfitRepo | None = None,
    log_outcome_result: str | None = "outcome-1",
    wardrobe_repo: _FakeWardrobeRepo | None = None,
) -> tuple[OutfitOutcomeService, _FakeSuggestionLogRepo, _FakeOutfitRepo]:
    log_repo = _FakeSuggestionLogRepo(impression=impression, log_outcome_result=log_outcome_result)
    o_repo = outfit_repo or _FakeOutfitRepo()
    w_repo = wardrobe_repo or _FakeWardrobeRepo()
    service = OutfitOutcomeService(
        suggestion_log_repo=log_repo, outfit_repo=o_repo, wardrobe_repo=w_repo
    )
    return service, log_repo, o_repo


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_saved_inserts_one_outfit_row_and_one_outcome_row() -> None:
    impression = _impression()
    service, log_repo, outfit_repo = _service(impression=impression)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="saved",
        client_occurred_at=None,
        name=None,
    )

    assert result["outfit_id"] == "outfit-1"
    assert result["already_saved"] is False
    assert result["outcome_recorded"] is True
    assert len(outfit_repo.insert_outfit_calls) == 1
    outfit = outfit_repo.insert_outfit_calls[0]
    assert outfit.session_id == "session-1"
    assert outfit.outfit_fingerprint == "a" * 64
    assert outfit.ai_generated is True
    assert outfit.items_snapshot  # populated, even if all-missing entries
    assert len(log_repo.log_outcome_calls) == 1
    logged = log_repo.log_outcome_calls[0]
    assert logged.outcome_type == "saved"
    assert logged.outfit_id == "outfit-1"


async def test_cross_tenant_impression_returns_404_and_performs_zero_writes() -> None:
    """The single most important test in this ticket (design §3)."""
    impression = _impression(user_id="victim-user")
    service, log_repo, outfit_repo = _service(impression=impression)

    with pytest.raises(OutcomeNotFoundError):
        await service.record_outcome(
            user_id="attacker-user",
            jwt="fake-jwt",
            session_id="session-1",
            rank=1,
            outcome_type="saved",
            client_occurred_at=None,
            name=None,
        )

    assert outfit_repo.insert_outfit_calls == []
    assert outfit_repo.insert_wear_calls == []
    assert log_repo.log_outcome_calls == []


async def test_impression_not_found_returns_404_no_writes() -> None:
    service, log_repo, outfit_repo = _service(impression=None)

    with pytest.raises(OutcomeNotFoundError):
        await service.record_outcome(
            user_id="user-1",
            jwt="fake-jwt",
            session_id="session-1",
            rank=1,
            outcome_type="saved",
            client_occurred_at=None,
            name=None,
        )

    assert outfit_repo.insert_outfit_calls == []
    assert log_repo.log_outcome_calls == []


async def test_repeat_saved_same_fingerprint_returns_already_saved_no_second_row() -> None:
    impression = _impression()
    outfit_repo = _FakeOutfitRepo(insert_result=("outfit-existing", True))
    service, log_repo, outfit_repo = _service(impression=impression, outfit_repo=outfit_repo)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="saved",
        client_occurred_at=None,
        name=None,
    )

    assert result["already_saved"] is True
    assert result["outfit_id"] == "outfit-existing"
    # insert_outfit is still called once (repository owns the dedupe logic
    # via ON CONFLICT) -- the service must not raise regardless.
    assert len(outfit_repo.insert_outfit_calls) == 1


async def test_dismissed_writes_outcome_row_and_no_outfits_row() -> None:
    impression = _impression()
    service, log_repo, outfit_repo = _service(impression=impression)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="dismissed",
        client_occurred_at=None,
        name=None,
    )

    assert result["outfit_id"] is None
    assert outfit_repo.insert_outfit_calls == []
    assert len(log_repo.log_outcome_calls) == 1
    assert log_repo.log_outcome_calls[0].outcome_type == "dismissed"
    assert log_repo.log_outcome_calls[0].outfit_id is None


async def test_worn_writes_outfit_and_one_wear_row_per_item_with_outfit_id_and_occasion() -> None:
    impression = _impression(item_ids=["item-a", "item-b", "item-c"], occasion="office")
    service, log_repo, outfit_repo = _service(impression=impression)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="worn",
        client_occurred_at=None,
        name=None,
    )

    assert result["outfit_id"] == "outfit-1"
    assert len(outfit_repo.insert_wear_calls) == 1
    call = outfit_repo.insert_wear_calls[0]
    assert call["item_ids"] == ["item-a", "item-b", "item-c"]
    assert call["outfit_id"] == "outfit-1"
    assert call["occasion_key"] == "office"
    assert call["worn_on"] == ist_today().isoformat()
    assert log_repo.log_outcome_calls[0].outcome_type == "worn"


async def test_worn_repeat_same_day_reports_already_logged_via_already_saved_flag() -> None:
    impression = _impression()
    outfit_repo = _FakeOutfitRepo(insert_wear_result=False)  # ON CONFLICT DO NOTHING -- nothing new
    service, log_repo, outfit_repo = _service(impression=impression, outfit_repo=outfit_repo)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="worn",
        client_occurred_at=None,
        name=None,
    )

    assert result["already_saved"] is True  # "already logged for today"


async def test_occasion_written_comes_from_session_row_never_from_request() -> None:
    """The request model has no occasion field at all -- this proves the
    written value is ImpressionRef.occasion regardless of anything else."""
    impression = _impression(occasion="office")
    service, log_repo, outfit_repo = _service(impression=impression)

    await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="saved",
        client_occurred_at=None,
        name="my totally different occasion outfit",  # not an occasion field -- irrelevant either way
    )

    assert outfit_repo.insert_outfit_calls[0].occasion == "office"


async def test_log_outcome_failing_still_returns_200_shape_and_does_not_roll_back_outfit() -> None:
    impression = _impression()
    service, log_repo, outfit_repo = _service(impression=impression, log_outcome_result=None)

    result = await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="saved",
        client_occurred_at=None,
        name=None,
    )

    assert result["outcome_recorded"] is False
    assert result["outfit_id"] == "outfit-1"  # the outfit write is NOT rolled back
    assert len(outfit_repo.insert_outfit_calls) == 1


async def test_items_snapshot_tolerates_fewer_resolved_rows_than_item_ids() -> None:
    impression = _impression(item_ids=["item-a", "item-b", "item-gone"])
    wardrobe_repo = _FakeWardrobeRepo(
        styling_rows=[{"id": "item-a", "category": "western_top", "color_primary": "#000000"}],
        image_info={"item-a": {"thumbnail_url": "https://example.com/a.jpg"}},
    )
    service, log_repo, outfit_repo = _service(impression=impression, wardrobe_repo=wardrobe_repo)

    await service.record_outcome(
        user_id="user-1",
        jwt="fake-jwt",
        session_id="session-1",
        rank=1,
        outcome_type="saved",
        client_occurred_at=None,
        name=None,
    )

    snapshot = outfit_repo.insert_outfit_calls[0].items_snapshot
    by_id = {entry["item_id"]: entry for entry in snapshot}
    assert by_id["item-a"]["category"] == "western_top"
    assert by_id["item-a"]["image_path"] == "https://example.com/a.jpg"
    assert by_id["item-gone"].get("missing") is True

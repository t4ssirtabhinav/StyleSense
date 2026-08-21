"""Tests for backend/adapters/wardrobe_repository.py (SS-011), mocked
``supabase-py`` async client -- no real network/DB calls.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from adapters.wardrobe_repository import SupabaseWardrobeRepository


class _FakeResponse:
    def __init__(self, data: Any) -> None:
        self.data = data


class _FakeQueryBuilder:
    """Records every chained call (method name + args/kwargs) and returns
    itself for chaining, except ``execute()`` which returns a canned
    ``_FakeResponse`` (async)."""

    def __init__(
        self, calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]], response_data: Any
    ) -> None:
        self._calls = calls
        self._response_data = response_data

    def _record(self, name: str, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        self._calls.append((name, args, kwargs))
        return self

    def upsert(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("upsert", *args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("update", *args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("delete", *args, **kwargs)

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("eq", *args, **kwargs)

    def in_(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("in_", *args, **kwargs)

    def limit(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("limit", *args, **kwargs)

    async def execute(self) -> _FakeResponse:
        self._calls.append(("execute", (), {}))
        return _FakeResponse(self._response_data)


class _FakePostgrest:
    def __init__(self) -> None:
        self.auth_calls: list[str] = []

    def auth(self, jwt: str) -> None:
        self.auth_calls.append(jwt)


class _FakeAsyncClient:
    def __init__(self, response_data: Any = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.postgrest = _FakePostgrest()
        self._response_data = response_data
        self.table_names: list[str] = []

    def table(self, name: str) -> _FakeQueryBuilder:
        self.table_names.append(name)
        return _FakeQueryBuilder(self.calls, self._response_data)


def _patch_acreate_client(fake_client: _FakeAsyncClient) -> Any:
    return patch(
        "adapters.wardrobe_repository.acreate_client",
        new=AsyncMock(return_value=fake_client),
    )


async def test_upsert_uploaded_row_uses_caller_supplied_item_id_and_uploaded_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient()
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        await repo.upsert_uploaded_row(
            jwt="caller-jwt",
            item_id="11111111-1111-1111-1111-111111111111",
            user_id="user-1",
            image_key="wardrobe/user-1/item-1/original.jpg",
        )

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["wardrobe_items"]

    upsert_call = next(c for c in fake_client.calls if c[0] == "upsert")
    payload = upsert_call[1][0]
    assert payload["id"] == "11111111-1111-1111-1111-111111111111"
    assert payload["category"] is None
    assert payload["processing_status"] == "uploaded"
    assert upsert_call[2]["ignore_duplicates"] is True
    assert upsert_call[2]["on_conflict"] == "id"


async def test_upsert_uploaded_row_is_idempotent_on_conflict_do_nothing_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    repo = SupabaseWardrobeRepository()

    fake_client_1 = _FakeAsyncClient()
    with _patch_acreate_client(fake_client_1):
        await repo.upsert_uploaded_row(
            jwt="caller-jwt", item_id="item-1", user_id="user-1", image_key="k"
        )

    fake_client_2 = _FakeAsyncClient()
    with _patch_acreate_client(fake_client_2):
        # A second call with the same item_id must not raise.
        await repo.upsert_uploaded_row(
            jwt="caller-jwt", item_id="item-1", user_id="user-1", image_key="k"
        )

    for fake_client in (fake_client_1, fake_client_2):
        upsert_call = next(c for c in fake_client.calls if c[0] == "upsert")
        assert upsert_call[2]["ignore_duplicates"] is True
        assert upsert_call[2]["on_conflict"] == "id"


async def test_update_bg_removal_result_merges_ai_tags_under_bg_removal_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    # Pre-existing ai_tags has an unrelated top-level key that must survive.
    fake_client = _FakeAsyncClient(response_data=[{"ai_tags": {"other_key": {"foo": "bar"}}}])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        await repo.update_bg_removal_result(
            jwt="caller-jwt",
            item_id="item-1",
            processing_status="bg_removed",
            image_clean_url="wardrobe/user-1/item-1/clean.png",
            thumbnail_url="wardrobe/user-1/item-1/thumbnail.jpg",
            bg_removal_tags={"source": "replicate", "low_confidence": False, "latency_ms": 1200},
        )

    update_call = next(c for c in fake_client.calls if c[0] == "update")
    payload = update_call[1][0]
    assert payload["ai_tags"]["other_key"] == {"foo": "bar"}
    assert payload["ai_tags"]["bg_removal"] == {
        "source": "replicate",
        "low_confidence": False,
        "latency_ms": 1200,
    }
    assert payload["processing_status"] == "bg_removed"
    assert payload["image_clean_url"] == "wardrobe/user-1/item-1/clean.png"
    assert payload["thumbnail_url"] == "wardrobe/user-1/item-1/thumbnail.jpg"


async def test_update_tagging_result_writes_columns_and_merges_ai_tags_under_tagging_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    # Pre-existing ai_tags has SS-011's bg_removal key, which must survive.
    fake_client = _FakeAsyncClient(
        response_data=[{"ai_tags": {"bg_removal": {"source": "replicate"}}}]
    )
    repo = SupabaseWardrobeRepository()

    tag_columns = {
        "category": "ethnic_kurta",
        "subcategory": "straight-fit kurta",
        "color_primary": "#1E3A8A",
        "color_secondary": None,
        "pattern": "block_print",
        "fabric": "cotton",
        "occasion_tags": ["festival", "puja"],
        "season_tags": ["summer"],
    }
    tagging_tags = {
        "status": "tagged",
        "source": "gemini",
        "confidence": 0.9,
        "flagged_for_review": False,
        "moderation": {"content_flag": "ok", "contains_person": False},
    }

    with _patch_acreate_client(fake_client):
        await repo.update_tagging_result(
            jwt="caller-jwt",
            item_id="item-1",
            tag_columns=tag_columns,
            tagging_tags=tagging_tags,
        )

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    update_call = next(c for c in fake_client.calls if c[0] == "update")
    payload = update_call[1][0]

    assert payload["ai_tags"]["bg_removal"] == {"source": "replicate"}
    assert payload["ai_tags"]["tagging"] == tagging_tags
    assert payload["category"] == "ethnic_kurta"
    assert payload["occasion_tags"] == ["festival", "puja"]
    assert payload["season_tags"] == ["summer"]


async def test_update_tagging_result_writes_no_columns_when_tag_columns_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[{"ai_tags": {"bg_removal": {"source": "replicate"}}}]
    )
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        await repo.update_tagging_result(
            jwt="caller-jwt",
            item_id="item-1",
            tag_columns=None,
            tagging_tags={"status": "failed"},
        )

    update_call = next(c for c in fake_client.calls if c[0] == "update")
    payload = update_call[1][0]

    assert payload["ai_tags"]["bg_removal"] == {"source": "replicate"}
    assert payload["ai_tags"]["tagging"] == {"status": "failed"}
    assert "category" not in payload
    assert "occasion_tags" not in payload


async def test_item_exists_returns_true_when_row_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[{"id": "item-1"}])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        exists = await repo.item_exists(jwt="caller-jwt", item_id="item-1")

    assert exists is True
    assert fake_client.postgrest.auth_calls == ["caller-jwt"]


async def test_item_exists_returns_false_when_row_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        exists = await repo.item_exists(jwt="caller-jwt", item_id="item-1")

    assert exists is False


async def test_get_plan_tier_scopes_select_to_callers_own_jwt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[{"plan_tier": "premium"}])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        plan_tier = await repo.get_plan_tier(jwt="caller-jwt", user_id="user-1")

    assert plan_tier == "premium"
    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["users"]
    select_call = next(c for c in fake_client.calls if c[0] == "select")
    assert select_call[1][0] == "plan_tier"


# --- SS-014: get_items_image_info_bulk --------------------------------------


async def test_get_items_image_info_bulk_returns_dict_keyed_by_id_rls_scoped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "id": "item-1",
                "image_url": "wardrobe/user-1/item-1/original.jpg",
                "image_clean_url": None,
                "thumbnail_url": "wardrobe/user-1/item-1/thumbnail.jpg",
                "processing_status": "bg_removed",
            },
            {
                "id": "item-2",
                "image_url": "wardrobe/user-1/item-2/original.jpg",
                "image_clean_url": None,
                "thumbnail_url": None,
                "processing_status": "bg_pending",
            },
        ]
    )
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.get_items_image_info_bulk(
            jwt="caller-jwt", item_ids=["item-1", "item-2", "item-3"]
        )

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["wardrobe_items"]
    in_call = next(c for c in fake_client.calls if c[0] == "in_")
    assert in_call[1] == ("id", ["item-1", "item-2", "item-3"])

    assert set(result.keys()) == {"item-1", "item-2"}
    assert result["item-1"]["thumbnail_url"] == "wardrobe/user-1/item-1/thumbnail.jpg"
    assert result["item-2"]["processing_status"] == "bg_pending"


async def test_get_items_image_info_bulk_returns_empty_dict_when_no_rows_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        result = await repo.get_items_image_info_bulk(jwt="caller-jwt", item_ids=["item-1"])

    assert result == {}


# --- SS-015: delete_item / get_item_image_info's thumbnail_url addition ----


async def test_get_item_image_info_selects_thumbnail_url_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "image_url": "wardrobe/user-1/item-1/original.jpg",
                "image_clean_url": "wardrobe/user-1/item-1/clean.png",
                "thumbnail_url": "wardrobe/user-1/item-1/thumbnail.jpg",
                "processing_status": "bg_removed",
            }
        ]
    )
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        info = await repo.get_item_image_info(jwt="caller-jwt", item_id="item-1")

    assert info is not None
    assert info["thumbnail_url"] == "wardrobe/user-1/item-1/thumbnail.jpg"
    select_call = next(c for c in fake_client.calls if c[0] == "select")
    assert "thumbnail_url" in select_call[1][0]


async def test_delete_item_issues_rls_scoped_delete_keyed_by_id_and_returns_true_when_a_row_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[{"id": "item-1"}])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        deleted = await repo.delete_item(jwt="caller-jwt", item_id="item-1")

    assert deleted is True
    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["wardrobe_items"]
    eq_call = next(c for c in fake_client.calls if c[0] == "eq")
    assert eq_call[1] == ("id", "item-1")


async def test_delete_item_returns_false_when_no_row_matched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        deleted = await repo.delete_item(jwt="caller-jwt", item_id="item-1")

    assert deleted is False


# --- SS-040: get_items_for_styling's select list must carry the lifecycle
# columns -- this is the single point of failure for the whole feature; if
# this test is ever reverted/weakened, do_not_style/is_archived silently
# become a permanent no-op even though every other layer is wired. ---------


async def test_get_items_for_styling_selects_lifecycle_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        await repo.get_items_for_styling(jwt="caller-jwt", user_id="user-1")

    select_call = next(c for c in fake_client.calls if c[0] == "select")
    selected = select_call[1][0]
    for column in ("do_not_style", "is_archived", "condition", "custom_tags"):
        assert column in selected


# --- SS-048: get_items_for_rails --------------------------------------------


async def test_get_items_for_rails_selects_created_at_and_lifecycle_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(response_data=[])
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        await repo.get_items_for_rails(jwt="caller-jwt", user_id="user-1")

    assert fake_client.postgrest.auth_calls == ["caller-jwt"]
    assert fake_client.table_names == ["wardrobe_items"]
    select_call = next(c for c in fake_client.calls if c[0] == "select")
    selected = select_call[1][0]
    # `created_at` is the field get_items_for_styling's own select list
    # omits -- the single point of failure for SS-048's newest_pieces rail.
    for column in ("created_at", "do_not_style", "is_archived", "wear_count", "color_primary"):
        assert column in selected


async def test_get_items_for_rails_returns_rows_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _FakeAsyncClient(
        response_data=[
            {
                "id": "item-1",
                "category": "ethnic_kurta",
                "color_primary": "#1E3A8A",
                "created_at": "2026-08-01T00:00:00Z",
                "wear_count": 0,
                "do_not_style": False,
                "is_archived": False,
            }
        ]
    )
    repo = SupabaseWardrobeRepository()

    with _patch_acreate_client(fake_client):
        rows = await repo.get_items_for_rails(jwt="caller-jwt", user_id="user-1")

    assert rows == [
        {
            "id": "item-1",
            "category": "ethnic_kurta",
            "color_primary": "#1E3A8A",
            "created_at": "2026-08-01T00:00:00Z",
            "wear_count": 0,
            "do_not_style": False,
            "is_archived": False,
        }
    ]

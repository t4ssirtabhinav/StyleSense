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

    def select(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("select", *args, **kwargs)

    def eq(self, *args: Any, **kwargs: Any) -> _FakeQueryBuilder:
        return self._record("eq", *args, **kwargs)

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

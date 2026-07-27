"""Tests for backend/services/wardrobe_deletion_service.py (SS-015)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.wardrobe_deletion_service import WardrobeDeletionService


async def test_cleanup_storage_calls_delete_objects_with_only_the_non_null_keys() -> None:
    storage = MagicMock()
    service = WardrobeDeletionService(storage)

    await service.cleanup_storage(
        user_id="user-1",
        item_id="item-1",
        keys=["wardrobe/user-1/item-1/original.jpg", None, "", "wardrobe/user-1/item-1/clean.png"],  # type: ignore[list-item]
    )

    storage.delete_objects.assert_called_once_with(
        ["wardrobe/user-1/item-1/original.jpg", "wardrobe/user-1/item-1/clean.png"]
    )


async def test_cleanup_storage_is_a_noop_when_all_keys_are_null_or_empty() -> None:
    storage = MagicMock()
    service = WardrobeDeletionService(storage)

    await service.cleanup_storage(user_id="user-1", item_id="item-1", keys=[])

    storage.delete_objects.assert_not_called()


async def test_cleanup_storage_swallows_and_logs_a_storage_exception_rather_than_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    storage = MagicMock()
    storage.delete_objects.side_effect = RuntimeError("R2 unreachable")
    service = WardrobeDeletionService(storage)

    with caplog.at_level("ERROR"):
        # Must not raise.
        await service.cleanup_storage(
            user_id="user-1",
            item_id="item-1",
            keys=["wardrobe/user-1/item-1/original.jpg"],
        )

    assert "wardrobe_item_delete_storage_cleanup_failed" in caplog.text

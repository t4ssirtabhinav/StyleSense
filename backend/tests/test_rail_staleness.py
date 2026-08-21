"""Tests for backend/services/rail_staleness.py (SS-048), against fake
repos -- no real network/DB calls, no real BackgroundTasks HTTP round-trip
(a real ``fastapi.BackgroundTasks`` instance is used since it's a plain
in-process list, not an I/O boundary)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import BackgroundTasks

from adapters.interfaces import ISuggestionRailsRepository, SuggestionRailRow
from services.app_config import AppConfigService, AppConfigSnapshot
from services.rail_staleness import maybe_trigger_rail_recompute


class _FakeRailsRepo(ISuggestionRailsRepository):
    def __init__(
        self, *, most_recent: datetime | None = None, raise_on_read: bool = False
    ) -> None:
        self._most_recent = most_recent
        self._raise_on_read = raise_on_read

    async def upsert_rails(self, **kwargs: Any) -> None:
        raise NotImplementedError

    async def get_rails(self, *, jwt: str, user_id: str) -> list[SuggestionRailRow]:
        raise NotImplementedError

    async def get_most_recent_computed_at(self, *, jwt: str, user_id: str) -> datetime | None:
        if self._raise_on_read:
            raise RuntimeError("db unreachable")
        return self._most_recent


class _RecordingRailPrecomputeService:
    """Duck-typed against ``RailPrecomputeService``'s own public shape --
    records calls instead of doing real work."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def recompute_all_rails(self, *, jwt: str, user_id: str) -> None:
        self.calls.append({"jwt": jwt, "user_id": user_id})


def _empty_app_config() -> tuple[AppConfigService, AppConfigSnapshot]:
    from adapters.interfaces import IAppConfigRepository

    class _EmptyConfigRepo(IAppConfigRepository):
        async def fetch_all(self) -> dict[str, Any]:
            return {}

    service = AppConfigService(_EmptyConfigRepo())
    snapshot = AppConfigSnapshot(values={}, fetched_at=0.0, stale=False)
    return service, snapshot


async def test_adds_background_task_when_no_row_exists_yet() -> None:
    rails_repo = _FakeRailsRepo(most_recent=None)
    precompute = _RecordingRailPrecomputeService()
    app_config, snapshot = _empty_app_config()
    background_tasks = BackgroundTasks()

    await maybe_trigger_rail_recompute(
        jwt="jwt",
        user_id="u1",
        background_tasks=background_tasks,
        rails_repo=rails_repo,
        rail_precompute_service=precompute,  # type: ignore[arg-type]
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert len(background_tasks.tasks) == 1
    await background_tasks()
    assert precompute.calls == [{"jwt": "jwt", "user_id": "u1"}]


async def test_adds_background_task_when_most_recent_is_older_than_debounce_window() -> None:
    stale_time = datetime.now(UTC) - timedelta(seconds=700)  # older than the 600s default
    rails_repo = _FakeRailsRepo(most_recent=stale_time)
    precompute = _RecordingRailPrecomputeService()
    app_config, snapshot = _empty_app_config()
    background_tasks = BackgroundTasks()

    await maybe_trigger_rail_recompute(
        jwt="jwt",
        user_id="u1",
        background_tasks=background_tasks,
        rails_repo=rails_repo,
        rail_precompute_service=precompute,  # type: ignore[arg-type]
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert len(background_tasks.tasks) == 1


async def test_does_not_add_background_task_when_within_debounce_window() -> None:
    fresh_time = datetime.now(UTC) - timedelta(seconds=60)  # within the 600s default
    rails_repo = _FakeRailsRepo(most_recent=fresh_time)
    precompute = _RecordingRailPrecomputeService()
    app_config, snapshot = _empty_app_config()
    background_tasks = BackgroundTasks()

    await maybe_trigger_rail_recompute(
        jwt="jwt",
        user_id="u1",
        background_tasks=background_tasks,
        rails_repo=rails_repo,
        rail_precompute_service=precompute,  # type: ignore[arg-type]
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert len(background_tasks.tasks) == 0


async def test_failed_staleness_check_is_swallowed_never_propagates() -> None:
    rails_repo = _FakeRailsRepo(raise_on_read=True)
    precompute = _RecordingRailPrecomputeService()
    app_config, snapshot = _empty_app_config()
    background_tasks = BackgroundTasks()

    # Must not raise.
    await maybe_trigger_rail_recompute(
        jwt="jwt",
        user_id="u1",
        background_tasks=background_tasks,
        rails_repo=rails_repo,
        rail_precompute_service=precompute,  # type: ignore[arg-type]
        config_snapshot=snapshot,
        app_config=app_config,
    )

    assert len(background_tasks.tasks) == 0

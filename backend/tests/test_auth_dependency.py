"""Tests for backend/dependencies/auth.py (SS-011, resolves BL-033).

Mocks ``supabase-py``'s ``create_client``/``Client.auth.get_user`` -- no
real network/Auth API calls. The call-shape asserted here (sync
``get_user(jwt) -> UserResponse | None``, raising on invalid token) was
independently confirmed against the actually-installed
``supabase==2.31.0``/``supabase-auth==2.31.0`` source during this ticket's
Developer phase (see the module's own docstring + docs/worklog/SS-011.md).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from dependencies.auth import get_current_user_id


def _fake_client(
    get_user_return: object = None, get_user_raises: Exception | None = None
) -> MagicMock:
    client = MagicMock()
    if get_user_raises is not None:
        client.auth.get_user.side_effect = get_user_raises
    else:
        client.auth.get_user.return_value = get_user_return
    return client


async def test_missing_authorization_header_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization=None)

    assert exc_info.value.status_code == 401


async def test_malformed_non_bearer_header_returns_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_id(authorization="Token abc123")

    assert exc_info.value.status_code == 401


async def test_token_rejected_by_get_user_raising_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _fake_client(get_user_raises=RuntimeError("invalid token"))

    with patch("dependencies.auth.create_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(authorization="Bearer bad-token")

    assert exc_info.value.status_code == 401


async def test_token_rejected_by_get_user_returning_no_user_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_client = _fake_client(get_user_return=None)

    with patch("dependencies.auth.create_client", return_value=fake_client):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user_id(authorization="Bearer some-token")

    assert exc_info.value.status_code == 401


async def test_valid_token_returns_resolved_user_id_as_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")

    fake_user_response = SimpleNamespace(user=SimpleNamespace(id="user-abc-123"))
    fake_client = _fake_client(get_user_return=fake_user_response)

    with patch("dependencies.auth.create_client", return_value=fake_client):
        user_id = await get_current_user_id(authorization="Bearer good-token")

    assert user_id == "user-abc-123"
    assert isinstance(user_id, str)
    fake_client.auth.get_user.assert_called_once_with("good-token")

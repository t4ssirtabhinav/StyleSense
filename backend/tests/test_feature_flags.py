"""Tests for backend/services/feature_flags.py (SS-026) -- design §7.3.

No real network calls -- ``Posthog`` is mocked at the construction site.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.feature_flags import FeatureFlagService


def test_no_api_key_returns_default_and_constructs_no_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POSTHOG_API_KEY", raising=False)

    with patch("services.feature_flags.Posthog") as mocked_posthog:
        service = FeatureFlagService()
        result = service.is_enabled("some_flag", "user-1", default=True)

    mocked_posthog.assert_not_called()
    assert result is True


@pytest.mark.parametrize("flag_value", [True, False])
def test_api_key_present_feature_enabled_result_passed_through(
    monkeypatch: pytest.MonkeyPatch, flag_value: bool
) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "test-key")
    mocked_client = MagicMock()
    mocked_client.feature_enabled.return_value = flag_value

    with patch("services.feature_flags.Posthog", return_value=mocked_client):
        service = FeatureFlagService()
        result = service.is_enabled("some_flag", "user-1", default=not flag_value)

    assert result is flag_value


def test_feature_enabled_returns_none_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "test-key")
    mocked_client = MagicMock()
    mocked_client.feature_enabled.return_value = None

    with patch("services.feature_flags.Posthog", return_value=mocked_client):
        service = FeatureFlagService()
        result = service.is_enabled("some_flag", "user-1", default=True)

    assert result is True


def test_feature_enabled_raises_logs_warning_returns_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "test-key")
    mocked_client = MagicMock()
    mocked_client.feature_enabled.side_effect = RuntimeError("posthog outage")

    with patch("services.feature_flags.Posthog", return_value=mocked_client):
        service = FeatureFlagService()
        with caplog.at_level("WARNING", logger="services.feature_flags"):
            result = service.is_enabled("some_flag", "user-1", default=False)

    assert result is False
    assert any(
        r.levelname == "WARNING" and "feature_flag_check_failed" in r.message
        for r in caplog.records
    )


def test_distinct_id_passed_through_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTHOG_API_KEY", "test-key")
    mocked_client = MagicMock()
    mocked_client.feature_enabled.return_value = True

    with patch("services.feature_flags.Posthog", return_value=mocked_client):
        service = FeatureFlagService()
        service.is_enabled("some_flag", "distinct-user-42")

    mocked_client.feature_enabled.assert_called_once_with("some_flag", "distinct-user-42")

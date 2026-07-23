"""Tests for backend/services/rate_limiter.py (SS-006)."""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from services.rate_limiter import RateLimiter


async def test_fails_open_when_upstash_env_vars_unset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = RateLimiter()

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-1")

    assert allowed is True
    assert any(r.message == "rate_limiter_fail_open" for r in caplog.records)


async def test_calls_upstash_rest_api_with_bearer_token_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    captured_calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_calls.append((url, kwargs))
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 1}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = RateLimiter(max_requests=5, window_seconds=60)
    allowed = await limiter.check_and_increment("user-2")

    assert allowed is True
    assert len(captured_calls) == 2  # incr + expire (first request in window)

    incr_url, incr_kwargs = captured_calls[0]
    assert "user-2" in incr_url
    assert incr_kwargs["headers"]["Authorization"] == "Bearer test-token-abc"

    expire_url, expire_kwargs = captured_calls[1]
    assert "user-2" in expire_url
    assert expire_kwargs["headers"]["Authorization"] == "Bearer test-token-abc"


async def test_denies_when_count_exceeds_max_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 10}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = RateLimiter(max_requests=5, window_seconds=60)
    allowed = await limiter.check_and_increment("user-3")

    assert allowed is False


async def test_fails_open_on_upstash_http_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    mock_post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    limiter = RateLimiter()

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-4")

    assert allowed is True
    assert any(r.message == "rate_limiter_error_fail_open" for r in caplog.records)

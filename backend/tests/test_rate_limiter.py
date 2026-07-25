"""Tests for backend/services/rate_limiter.py (SS-006, updated SS-018, SS-011
adds DailyRateLimiter)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest

from services.rate_limiter import DailyRateLimiter, RateLimiter, _seconds_until_next_ist_midnight


async def test_fails_closed_when_upstash_env_vars_unset_by_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = RateLimiter()

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-1")

    assert allowed is False
    env_unset_records = [r for r in caplog.records if r.message == "rate_limiter_env_unset"]
    assert len(env_unset_records) == 1
    assert env_unset_records[0].fail_open is False  # type: ignore[attr-defined]


async def test_fail_open_opt_in_when_upstash_env_vars_unset(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = RateLimiter(fail_open=True)

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-1")

    assert allowed is True
    env_unset_records = [r for r in caplog.records if r.message == "rate_limiter_env_unset"]
    assert len(env_unset_records) == 1
    assert env_unset_records[0].fail_open is True  # type: ignore[attr-defined]


async def test_calls_upstash_rest_api_with_bearer_token_and_nx_flag_when_configured(
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
    assert len(captured_calls) == 2

    incr_url, incr_kwargs = captured_calls[0]
    assert incr_url.endswith("/incr/stylesense:outfit_suggestions:rate_limit:user-2")
    assert incr_kwargs["headers"]["Authorization"] == "Bearer test-token-abc"

    expire_url, expire_kwargs = captured_calls[1]
    assert expire_url.endswith("/expire/stylesense:outfit_suggestions:rate_limit:user-2/60/NX")
    assert expire_kwargs["headers"]["Authorization"] == "Bearer test-token-abc"


async def test_expire_called_unconditionally_regardless_of_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    captured_calls: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_calls.append(url)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 3}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = RateLimiter(max_requests=5, window_seconds=60)
    allowed = await limiter.check_and_increment("user-race")

    assert allowed is True
    assert len(captured_calls) == 2
    assert captured_calls[1].endswith("/NX")


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


async def test_fails_closed_on_upstash_incr_http_error_by_default(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    mock_post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    limiter = RateLimiter()

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-4")

    assert allowed is False
    assert any(r.message == "rate_limiter_incr_error" for r in caplog.records)


async def test_fail_open_opt_in_on_upstash_incr_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    mock_post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    limiter = RateLimiter(fail_open=True)

    allowed = await limiter.check_and_increment("user-4")

    assert allowed is True


async def test_expire_failure_does_not_override_allow_decision(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if "/incr/" in url:
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"result": 1}, request=request)
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = RateLimiter(max_requests=5, window_seconds=60)

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-5")

    assert allowed is True
    assert any(r.message == "rate_limiter_expire_error" for r in caplog.records)


async def test_upstash_error_body_on_incr_treated_as_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"error": "ERR something"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = RateLimiter()

    with caplog.at_level(logging.WARNING):
        allowed = await limiter.check_and_increment("user-6")

    assert allowed is False
    assert any(r.message == "rate_limiter_incr_error" for r in caplog.records)


# ---------------------------------------------------------------------------
# DailyRateLimiter (SS-011)
# ---------------------------------------------------------------------------


async def test_daily_limiter_skip_true_returns_true_with_zero_http_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    mock_post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    limiter = DailyRateLimiter(max_requests=20)
    allowed = await limiter.check_and_increment("premium-user", skip=True)

    assert allowed is True
    mock_post.assert_not_called()


async def test_daily_limiter_uses_exact_bg_remove_key_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    captured_urls: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_urls.append(url)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 1}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    limiter = DailyRateLimiter(max_requests=20)
    allowed = await limiter.check_and_increment("user-daily-1")

    assert allowed is True
    incr_url = captured_urls[0]
    assert incr_url.endswith(f"/incr/bg_remove:user-daily-1:{ist_today}")
    # Explicitly not the existing RateLimiter's key-prefix style.
    assert "stylesense:outfit_suggestions:rate_limit" not in incr_url


async def test_daily_limiter_expire_uses_seconds_until_next_ist_midnight_not_fixed_86400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    captured_urls: list[str] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured_urls.append(url)
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 1}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    expected_ttl = _seconds_until_next_ist_midnight()
    limiter = DailyRateLimiter(max_requests=20)
    await limiter.check_and_increment("user-daily-2")

    expire_url = captured_urls[1]
    assert "/expire/bg_remove:user-daily-2:" in expire_url
    assert "/NX" in expire_url

    # Extract the TTL segment and assert it's close to the freshly computed
    # "seconds until next IST midnight" value, not a fixed 86400.
    ttl_segment = expire_url.split("/expire/", 1)[1].rsplit("/NX", 1)[0]
    ttl_seconds = int(ttl_segment.rsplit("/", 1)[1])
    assert ttl_seconds != 86400
    assert abs(ttl_seconds - expected_ttl) <= 5


async def test_daily_limiter_allows_at_boundary_count_20_denies_at_21(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    async def make_fake_post(count: int) -> Any:
        async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
            request = httpx.Request("POST", url)
            if "/incr/" in url:
                return httpx.Response(200, json={"result": count}, request=request)
            return httpx.Response(200, json={"result": 1}, request=request)

        return fake_post

    monkeypatch.setattr(httpx.AsyncClient, "post", await make_fake_post(20))
    limiter = DailyRateLimiter(max_requests=20)
    assert await limiter.check_and_increment("user-boundary") is True

    monkeypatch.setattr(httpx.AsyncClient, "post", await make_fake_post(21))
    limiter = DailyRateLimiter(max_requests=20)
    assert await limiter.check_and_increment("user-boundary") is False


async def test_daily_limiter_fails_closed_by_default_when_upstash_env_vars_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = DailyRateLimiter(max_requests=20)
    allowed = await limiter.check_and_increment("user-no-upstash")

    assert allowed is False

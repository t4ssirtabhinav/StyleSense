"""Tests for backend/adapters/upstash_rate_limiter.py (SS-029 design §6.3).
Fake httpx transport, no network."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from adapters.upstash_rate_limiter import UpstashRateLimiter


def _install_fake_post(
    monkeypatch: pytest.MonkeyPatch, handler: Any
) -> list[tuple[str, str]]:
    """Returns a list of (method_kind, url) tuples appended by handler."""
    calls: list[tuple[str, str]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        calls.append(("POST", url))
        return await handler(url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return calls


async def test_incrby_decides_from_returned_total_in_one_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 5}, request=request)

    calls = _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=5, ceiling=10, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is True
    assert decision.current == 5
    assert decision.degraded is False
    incrby_calls = [url for _, url in calls if "/incrby/" in url]
    get_calls = [url for _, url in calls if "/get/" in url]
    assert len(incrby_calls) == 1
    assert incrby_calls[0].endswith("/incrby/k/5")
    assert get_calls == []  # structural guard: never a GET before the decision


async def test_expire_nx_called_unconditionally_after_every_incrby(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 1}, request=request)

    calls = _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    await limiter.check_and_consume(key="k", amount=1, ceiling=100, ttl_seconds=60, fail_open=False)

    expire_calls = [url for _, url in calls if "/expire/" in url]
    assert len(expire_calls) == 1
    assert expire_calls[0].endswith("/expire/k/60/NX")


async def test_expire_failure_does_not_flip_the_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        if "/incrby/" in url:
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"result": 1}, request=request)
        raise httpx.ConnectError("boom")

    _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=1, ceiling=100, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is True
    assert decision.degraded is False


async def test_fails_closed_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=1, ceiling=10, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is False
    assert decision.current is None
    assert decision.degraded is True


async def test_fails_closed_on_rest_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=1, ceiling=10, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is False
    assert decision.degraded is True


async def test_fails_open_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=1, ceiling=10, ttl_seconds=60, fail_open=True
    )

    assert decision.allowed is True
    assert decision.degraded is True


async def test_error_key_in_json_body_is_treated_as_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"error": "ERR bad"}, request=request)

    _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=1, ceiling=10, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is False
    assert decision.degraded is True


async def test_over_ceiling_denies_and_self_refunds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 11}, request=request)

    calls = _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    decision = await limiter.check_and_consume(
        key="k", amount=11, ceiling=10, ttl_seconds=60, fail_open=False
    )

    assert decision.allowed is False
    assert decision.current == 11
    decrby_calls = [url for _, url in calls if "/decrby/" in url]
    assert len(decrby_calls) == 1
    assert decrby_calls[0].endswith("/decrby/k/11")


async def test_adjust_uses_decrby_for_negative_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 0}, request=request)

    calls = _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    await limiter.adjust(key="k", delta=-42)

    assert len(calls) == 1
    url = calls[0][1]
    assert url.endswith("/decrby/k/42")
    assert "-" not in url.rsplit("/decrby/", 1)[1]


async def test_adjust_uses_incrby_for_positive_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def handler(url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 42}, request=request)

    calls = _install_fake_post(monkeypatch, handler)

    limiter = UpstashRateLimiter()
    await limiter.adjust(key="k", delta=42)

    assert calls[0][1].endswith("/incrby/k/42")


async def test_adjust_never_raises_on_rest_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = UpstashRateLimiter()
    await limiter.adjust(key="k", delta=-5)  # must not raise


async def test_adjust_zero_delta_is_a_no_op(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    mock_post_called = False

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        nonlocal mock_post_called
        mock_post_called = True
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 0}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    limiter = UpstashRateLimiter()
    await limiter.adjust(key="k", delta=0)

    assert mock_post_called is False


async def test_adjust_env_unset_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    limiter = UpstashRateLimiter()
    await limiter.adjust(key="k", delta=-5)  # must not raise

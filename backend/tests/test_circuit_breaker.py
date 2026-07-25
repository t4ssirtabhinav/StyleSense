"""Tests for backend/services/circuit_breaker.py (SS-011).

Note the deliberately opposite fail-mode from DailyRateLimiter (see
test_rate_limiter.py's DailyRateLimiter cases): this circuit breaker fails
"closed-circuit" (i.e. proceeds, `is_open() -> False`) on Redis-unavailable,
since it's a resilience heuristic, not a money gate.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from services.circuit_breaker import CircuitBreaker


class _FakeUpstash:
    """In-memory stand-in for Upstash's REST API, just enough surface for
    CircuitBreaker's GET/INCR/SET calls."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}

    async def handle(self, url: str) -> httpx.Response:
        request = httpx.Request("POST", url)
        # URL shape: {base}/{command}/{key}[/{value}] -- {key} itself
        # contains ":" but never "/", so splitting on "/" and matching the
        # known command tokens (rather than positional guessing) is robust.
        path = url.split("://", 1)[1].split("/", 1)[1]  # strip scheme+host
        segments = path.split("/")

        if segments[0] == "get":
            key = segments[1]
            return httpx.Response(200, json={"result": self.store.get(key)}, request=request)
        if segments[0] == "incr":
            key = segments[1]
            self.store[key] = int(self.store.get(key, 0)) + 1
            return httpx.Response(200, json={"result": self.store[key]}, request=request)
        if segments[0] == "set":
            key, value = segments[1], segments[2]
            self.store[key] = value
            return httpx.Response(200, json={"result": "OK"}, request=request)
        raise AssertionError(f"unexpected command in url: {url}")


@pytest.fixture
def fake_upstash(monkeypatch: pytest.MonkeyPatch) -> _FakeUpstash:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    fake = _FakeUpstash()

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        return await fake.handle(url)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    return fake


async def test_is_open_false_initially_with_no_failures_recorded(
    fake_upstash: _FakeUpstash,
) -> None:
    breaker = CircuitBreaker(failure_threshold=3, open_seconds=60)

    assert await breaker.is_open() is False


async def test_is_open_becomes_true_after_three_consecutive_failures(
    fake_upstash: _FakeUpstash,
) -> None:
    breaker = CircuitBreaker(failure_threshold=3, open_seconds=60)

    await breaker.record_failure()
    await breaker.record_failure()
    assert await breaker.is_open() is False

    await breaker.record_failure()
    assert await breaker.is_open() is True


async def test_record_success_resets_consecutive_failures(fake_upstash: _FakeUpstash) -> None:
    breaker = CircuitBreaker(failure_threshold=3, open_seconds=60)

    await breaker.record_failure()
    await breaker.record_failure()
    await breaker.record_success()
    await breaker.record_failure()
    await breaker.record_failure()

    # Only 2 consecutive failures since the reset -- circuit should still be
    # closed (not open).
    assert await breaker.is_open() is False


async def test_is_open_fails_closed_circuit_when_upstash_env_vars_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    breaker = CircuitBreaker()

    assert await breaker.is_open() is False


async def test_is_open_fails_closed_circuit_when_rest_call_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token-abc")

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    breaker = CircuitBreaker()

    assert await breaker.is_open() is False

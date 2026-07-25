"""Tests for backend/services/tag_cache.py (SS-012, amended A1), mocked
Upstash REST -- same ``monkeypatch.setattr(httpx.AsyncClient, "post", ...)``
convention this repo's RateLimiter/CircuitBreaker tests already use.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from services.tag_cache import TagCache


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")


async def test_get_returns_parsed_payload_on_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    payload = {"category": "ethnic_kurta", "confidence": 0.9}

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        assert url == "https://example-upstash.io"
        assert kwargs["json"] == ["GET", "tag:abc123"]
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": json.dumps(payload)}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    result = await cache.get("abc123")

    assert result == payload


async def test_get_returns_none_on_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": None}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    result = await cache.get("abc123")

    assert result is None


async def test_set_issues_result_key_with_30_day_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: list[list[Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured.append(kwargs["json"])
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": "OK"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    await cache.set("abc123", {"category": "ethnic_kurta"})

    assert len(captured) == 1
    command = captured[0]
    assert command[0] == "SET"
    assert command[1] == "tag:abc123"
    assert json.loads(command[2]) == {"category": "ethnic_kurta"}
    assert command[3] == "EX"
    assert command[4] == "2592000"


async def test_mark_inflight_uses_nx_and_60s_ttl_and_returns_true_on_first_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    captured: list[list[Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured.append(kwargs["json"])
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": "OK"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    result = await cache.mark_inflight("abc123")

    assert result is True
    command = captured[0]
    assert command == ["SET", "tag_inflight:abc123", "1", "EX", "60", "NX"]


async def test_mark_inflight_returns_false_when_marker_already_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": None}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    result = await cache.mark_inflight("abc123")

    assert result is False


async def test_clear_inflight_issues_del(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)
    captured: list[list[Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured.append(kwargs["json"])
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": 1}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()
    await cache.clear_inflight("abc123")

    assert captured[0] == ["DEL", "tag_inflight:abc123"]


async def test_fails_open_when_env_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    cache = TagCache()

    assert await cache.get("abc123") is None
    await cache.set("abc123", {"a": 1})  # no raise
    assert await cache.mark_inflight("abc123") is True
    await cache.clear_inflight("abc123")  # no raise


async def test_fails_open_when_upstash_rest_call_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = TagCache()

    assert await cache.get("abc123") is None
    await cache.set("abc123", {"a": 1})  # no raise
    assert await cache.mark_inflight("abc123") is True
    await cache.clear_inflight("abc123")  # no raise

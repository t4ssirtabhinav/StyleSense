"""Tests for backend/services/weather_cache.py (SS-022), mocked Upstash
REST -- same convention as tests/test_tag_cache.py."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from services.weather_cache import WeatherCache, _ist_hour


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", "https://example-upstash.io")
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")


async def test_set_issues_set_command_with_expected_key_and_ttl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr("services.weather_cache._ist_hour", lambda: "2026-08-14T10")
    captured: list[list[Any]] = []

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        captured.append(kwargs["json"])
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": "OK"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = WeatherCache()
    await cache.set("mumbai", {"temp_c": 28.2})

    command = captured[0]
    assert command[0] == "SET"
    assert command[1] == "weather:v1:mumbai:2026-08-14T10"
    assert json.loads(command[2]) == {"temp_c": 28.2}
    assert command[3] == "EX"
    assert command[4] == "3600"


async def test_ist_hour_format() -> None:
    hour = _ist_hour()
    # "%Y-%m-%dT%H" -- exactly 13 chars, e.g. "2026-08-14T10"
    assert len(hour) == 13
    assert hour[4] == "-" and hour[7] == "-" and hour[10] == "T"


async def test_round_trip_set_then_get_returns_same_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    store: dict[str, str] = {}

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        command = kwargs["json"]
        request = httpx.Request("POST", url)
        if command[0] == "SET":
            store[command[1]] = command[2]
            return httpx.Response(200, json={"result": "OK"}, request=request)
        if command[0] == "GET":
            return httpx.Response(200, json={"result": store.get(command[1])}, request=request)
        raise AssertionError(f"unexpected command {command}")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = WeatherCache()
    payload = {"temp_c": 28.2, "weather_code": 3}
    await cache.set("mumbai", payload)
    result = await cache.get("mumbai")

    assert result == payload


async def test_get_returns_none_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    cache = WeatherCache()
    assert await cache.get("mumbai") is None


async def test_set_is_noop_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    cache = WeatherCache()
    await cache.set("mumbai", {"temp_c": 28.2})  # no raise


async def test_corrupt_non_json_value_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": "not-json{"}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = WeatherCache()
    assert await cache.get("mumbai") is None


async def test_corrupt_json_but_not_a_dict_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        request = httpx.Request("POST", url)
        return httpx.Response(200, json={"result": json.dumps([1, 2, 3])}, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = WeatherCache()
    assert await cache.get("mumbai") is None


async def test_fails_open_when_upstash_rest_call_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_env(monkeypatch)

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    cache = WeatherCache()
    assert await cache.get("mumbai") is None
    await cache.set("mumbai", {"a": 1})  # no raise

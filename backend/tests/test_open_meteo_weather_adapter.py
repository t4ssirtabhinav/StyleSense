"""Tests for backend/adapters/open_meteo_weather_adapter.py (SS-022),
mocked httpx -- no network."""

from __future__ import annotations

from typing import Any

import httpx

from adapters.open_meteo_weather_adapter import OpenMeteoWeatherAdapter


def _mock_transport(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_well_formed_response_maps_field_by_field() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["latitude"] == "19.076"
        assert request.url.params["longitude"] == "72.8777"
        assert (
            request.url.params["current"]
            == "temperature_2m,relative_humidity_2m,weather_code,precipitation"
        )
        assert request.url.params["timezone"] == "Asia/Kolkata"
        return httpx.Response(
            200,
            json={
                "current": {
                    "time": "2026-08-14T10:45",
                    "temperature_2m": 28.2,
                    "relative_humidity_2m": 79,
                    "weather_code": 53,
                    "precipitation": 0.2,
                }
            },
        )

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    obs = await adapter.fetch_current(lat=19.076, lng=72.8777)

    assert obs is not None
    assert obs.temp_c == 28.2
    assert obs.humidity == 79
    assert obs.weather_code == 53
    assert obs.precipitation_mm == 0.2
    assert obs.observed_at == "2026-08-14T10:45"


async def test_http_500_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server error"})

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None


async def test_connect_timeout_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout")

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None


async def test_read_timeout_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timeout")

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None


async def test_invalid_json_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None


async def test_empty_current_object_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"current": {}})

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None


async def test_body_missing_weather_code_returns_none_never_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "current": {
                    "time": "2026-08-14T10:45",
                    "temperature_2m": 28.2,
                    "relative_humidity_2m": 79,
                    "precipitation": 0.2,
                }
            },
        )

    adapter = OpenMeteoWeatherAdapter(client=_mock_transport(handler))
    assert await adapter.fetch_current(lat=19.076, lng=72.8777) is None

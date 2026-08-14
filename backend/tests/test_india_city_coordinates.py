"""Tests for backend/services/india_city_coordinates.py (SS-022)."""

from __future__ import annotations

import pytest

from services.india_city_coordinates import CITY_COORDINATES, resolve_city

_ALL_CITY_NAMES = [city.name for city in CITY_COORDINATES.values()]


@pytest.mark.parametrize("name", _ALL_CITY_NAMES)
def test_every_top_50_city_display_name_resolves(name: str) -> None:
    """Direct guard against a transcription typo -- every one of the 50
    TOP_50_INDIAN_CITIES display names must resolve."""
    resolved = resolve_city(name)
    assert resolved is not None
    assert resolved.name == name


def test_exactly_fifty_cities_transcribed() -> None:
    assert len(CITY_COORDINATES) == 50


def test_whitespace_and_case_insensitive() -> None:
    a = resolve_city("  mumbai ")
    b = resolve_city("MUMBAI")
    c = resolve_city("Mumbai")
    assert a is not None and b is not None and c is not None
    assert a == b == c


def test_bangalore_alias_resolves_to_bengaluru() -> None:
    resolved = resolve_city("Bangalore")
    assert resolved is not None
    assert resolved.slug == "bengaluru"


def test_bombay_alias_resolves_to_mumbai() -> None:
    resolved = resolve_city("Bombay")
    assert resolved is not None
    assert resolved.slug == "mumbai"


def test_gurgaon_alias_resolves_to_delhi() -> None:
    resolved = resolve_city("Gurgaon")
    assert resolved is not None
    assert resolved.slug == "delhi"


@pytest.mark.parametrize("raw", [None, "", "   ", "Kanp", "Springfield"])
def test_unresolvable_input_returns_none(raw: str | None) -> None:
    assert resolve_city(raw) is None


def test_pimpri_chinchwad_hyphen_and_underscore_resolve_identically() -> None:
    hyphenated = resolve_city("Pimpri-Chinchwad")
    underscored = resolve_city("pimpri_chinchwad")
    assert hyphenated is not None
    assert underscored is not None
    assert hyphenated == underscored


def test_id_fallback_key_resolves() -> None:
    """The city id (not just the display name) is accepted as a fallback
    match key."""
    resolved = resolve_city("mumbai")
    assert resolved is not None
    assert resolved.slug == "mumbai"

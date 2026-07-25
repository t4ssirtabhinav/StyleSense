"""Tests for backend/ai/ports/interfaces.py (SS-006, extended SS-012)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai.ports.interfaces import (
    GarmentTags,
    IBackgroundRemovalProvider,
    IStylingProvider,
    IVisionProvider,
)


def test_istylingprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IStylingProvider()  # type: ignore[abstract]


def test_ibackgroundremovalprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IBackgroundRemovalProvider()  # type: ignore[abstract]


# --- SS-012: IVisionProvider / GarmentTags ---------------------------------


def test_ivisionprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IVisionProvider()  # type: ignore[abstract]


def test_garmenttags_rejects_category_not_in_the_21_value_enum() -> None:
    with pytest.raises(ValidationError):
        GarmentTags(
            category="not_a_real_category",  # type: ignore[arg-type]
            confidence=0.9,
            content_flag="ok",
            contains_person=False,
        )


def test_garmenttags_accepts_null_category_with_zero_confidence() -> None:
    tags = GarmentTags(
        category=None,
        confidence=0.0,
        content_flag="not_clothing",
        contains_person=False,
    )
    assert tags.category is None
    assert tags.confidence == 0.0


def test_garmenttags_rejects_occasion_tag_outside_the_12_value_enum() -> None:
    with pytest.raises(ValidationError):
        GarmentTags(
            category="western_top",
            occasion_tags=["not_a_real_occasion"],  # type: ignore[list-item]
            confidence=0.9,
            content_flag="ok",
            contains_person=False,
        )


def test_garmenttags_parses_a_fully_valid_ethnic_payload() -> None:
    tags = GarmentTags(
        category="ethnic_kurta",
        subcategory="straight-fit kurta",
        color_primary="#1E3A8A",
        color_secondary="#FFFFFF",
        pattern="block_print",
        fabric="cotton",
        occasion_tags=["festival", "puja"],
        season_tags=["summer", "all"],
        confidence=0.9,
        content_flag="ok",
        contains_person=False,
    )
    assert tags.category == "ethnic_kurta"
    assert tags.occasion_tags == ["festival", "puja"]
    assert tags.season_tags == ["summer", "all"]
    assert tags.content_flag == "ok"
    assert tags.contains_person is False


def test_garmenttags_drops_unknown_season_tags_instead_of_failing() -> None:
    tags = GarmentTags(
        category="western_top",
        season_tags=["summer", "spooky_season"],  # type: ignore[list-item]
        confidence=0.9,
        content_flag="ok",
        contains_person=False,
    )
    assert tags.season_tags == ["summer"]


def test_garmenttags_requires_contains_person_as_a_bool() -> None:
    with pytest.raises(ValidationError):
        GarmentTags(
            category="western_top",
            confidence=0.9,
            content_flag="ok",
        )  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        GarmentTags(
            category="western_top",
            confidence=0.9,
            content_flag="ok",
            contains_person="not-a-bool",  # type: ignore[arg-type]
        )

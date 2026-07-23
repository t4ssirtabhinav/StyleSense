"""Tests for backend/ai/ports/interfaces.py (SS-006)."""

from __future__ import annotations

import pytest

from ai.ports.interfaces import IStylingProvider


def test_istylingprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IStylingProvider()  # type: ignore[abstract]

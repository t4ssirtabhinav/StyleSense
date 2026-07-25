"""Tests for backend/ai/ports/interfaces.py (SS-006)."""

from __future__ import annotations

import pytest

from ai.ports.interfaces import IBackgroundRemovalProvider, IStylingProvider


def test_istylingprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IStylingProvider()  # type: ignore[abstract]


def test_ibackgroundremovalprovider_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        IBackgroundRemovalProvider()  # type: ignore[abstract]

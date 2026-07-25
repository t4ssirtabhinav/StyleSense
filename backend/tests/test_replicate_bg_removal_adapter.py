"""Tests for backend/ai/adapters/replicate_bg_removal_adapter.py (SS-011)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from replicate.helpers import FileOutput

from ai.adapters.replicate_bg_removal_adapter import MODEL_REFERENCE, ReplicateBgRemovalAdapter


class _FakeClient:
    pass


def _make_file_output(data: bytes) -> FileOutput:
    output = FileOutput.__new__(FileOutput)
    output.url = "https://replicate.delivery/fake/clean.png"

    async def _aread() -> bytes:
        return data

    output.aread = _aread  # type: ignore[method-assign]
    return output


async def test_calls_replicate_sdk_with_configured_model_and_image_bytes() -> None:
    fake_output = _make_file_output(b"clean-png-bytes")

    with patch(
        "ai.adapters.replicate_bg_removal_adapter.replicate.async_run",
        new=AsyncMock(return_value=fake_output),
    ) as mock_run:
        adapter = ReplicateBgRemovalAdapter()
        result = await adapter.remove_background(b"original-jpeg-bytes")

    assert result.success is True
    mock_run.assert_called_once()
    call_args = mock_run.call_args
    assert call_args.args[0] == MODEL_REFERENCE
    assert "image" in call_args.kwargs["input"]


async def test_returns_success_result_with_image_bytes_and_latency_on_success() -> None:
    fake_output = _make_file_output(b"clean-png-bytes")

    with patch(
        "ai.adapters.replicate_bg_removal_adapter.replicate.async_run",
        new=AsyncMock(return_value=fake_output),
    ):
        adapter = ReplicateBgRemovalAdapter()
        result = await adapter.remove_background(b"original-jpeg-bytes")

    assert result.success is True
    assert result.image_bytes == b"clean-png-bytes"
    assert result.latency_ms is not None
    assert result.latency_ms >= 0


async def test_returns_failure_result_instead_of_propagating_sdk_exception() -> None:
    async def _raise(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Insufficient credit")

    with patch("ai.adapters.replicate_bg_removal_adapter.replicate.async_run", new=_raise):
        adapter = ReplicateBgRemovalAdapter()
        result = await adapter.remove_background(b"original-jpeg-bytes")

    assert result.success is False
    assert result.image_bytes is None
    assert result.error is not None

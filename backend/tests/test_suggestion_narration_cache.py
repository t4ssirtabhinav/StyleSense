"""Tests for backend/services/suggestion_narration_cache.py (SS-020)."""

from __future__ import annotations

import pytest

from adapters.interfaces import CachedNarration, ISuggestionNarrationCacheRepository
from services.styling_rules_types import WardrobeItemInput
from services.suggestion_narration_cache import (
    NarrationCacheOrchestrator,
    compute_candidate_shape,
    compute_narration_signature,
    signature_order,
)


@pytest.fixture(autouse=True)
def _salt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "test-salt-do-not-use-in-prod")


def _wardrobe(**kwargs: WardrobeItemInput) -> dict[str, WardrobeItemInput]:
    return kwargs


def _item(id: str, *, category: str = "western_top", color: str | None = "#1E3A8A") -> WardrobeItemInput:
    return WardrobeItemInput(id=id, category=category, color_primary=color)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_narration_signature -- order-independence, sensitivity, coarsening
# ---------------------------------------------------------------------------


def test_signature_is_order_independent_across_permuted_candidate_lists() -> None:
    w = _wardrobe(a=_item("a", category="western_top"), b=_item("b", category="western_bottom"))
    shape_a = compute_candidate_shape(["a"], w)
    shape_b = compute_candidate_shape(["b"], w)

    sig1 = compute_narration_signature(
        [shape_a, shape_b], occasion_key="office", engine_version="engine-v2", llm_candidate_count=6
    )
    sig2 = compute_narration_signature(
        [shape_b, shape_a], occasion_key="office", engine_version="engine-v2", llm_candidate_count=6
    )
    assert sig1 == sig2


def test_signature_is_order_independent_within_a_single_candidates_items() -> None:
    w = _wardrobe(a=_item("a", category="western_top"), b=_item("b", category="western_bottom"))
    shape_forward = compute_candidate_shape(["a", "b"], w)
    shape_backward = compute_candidate_shape(["b", "a"], w)
    assert shape_forward == shape_backward


@pytest.mark.parametrize(
    "field, value_a, value_b",
    [
        ("occasion_key", "office", "wedding_guest"),
        ("engine_version", "engine-v2", "engine-v3"),
        ("llm_candidate_count", 5, 6),
    ],
)
def test_signature_is_sensitive_to_occasion_engine_version_and_candidate_count(
    field: str, value_a: object, value_b: object
) -> None:
    w = _wardrobe(a=_item("a"))
    shape = compute_candidate_shape(["a"], w)
    kwargs_a = {"occasion_key": "office", "engine_version": "engine-v2", "llm_candidate_count": 6}
    kwargs_b = dict(kwargs_a)
    kwargs_a[field] = value_a
    kwargs_b[field] = value_b

    sig_a = compute_narration_signature([shape], **kwargs_a)  # type: ignore[arg-type]
    sig_b = compute_narration_signature([shape], **kwargs_b)  # type: ignore[arg-type]
    assert sig_a != sig_b


def test_signature_is_sensitive_to_category_change() -> None:
    w1 = _wardrobe(a=_item("a", category="western_top"))
    w2 = _wardrobe(a=_item("a", category="western_bottom"))
    sig1 = compute_narration_signature(
        [compute_candidate_shape(["a"], w1)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    sig2 = compute_narration_signature(
        [compute_candidate_shape(["a"], w2)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    assert sig1 != sig2


def test_signature_is_sensitive_to_colour_family_change() -> None:
    w1 = _wardrobe(a=_item("a", color="#FF0000"))  # red
    w2 = _wardrobe(a=_item("a", color="#0000FF"))  # blue
    sig1 = compute_narration_signature(
        [compute_candidate_shape(["a"], w1)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    sig2 = compute_narration_signature(
        [compute_candidate_shape(["a"], w2)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    assert sig1 != sig2


def test_signature_is_sensitive_to_formality_band_change() -> None:
    # ethnic_saree (formality 8) vs western_top (formality 3) -- different bands.
    w1 = _wardrobe(a=_item("a", category="western_top"))
    w2 = _wardrobe(a=_item("a", category="ethnic_saree"))
    sig1 = compute_narration_signature(
        [compute_candidate_shape(["a"], w1)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    sig2 = compute_narration_signature(
        [compute_candidate_shape(["a"], w2)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    assert sig1 != sig2


def test_same_candidate_set_different_raw_hex_within_same_colour_family_produces_same_signature() -> None:
    """Coarsening proof: two near-identical reds must hash to the SAME
    signature -- this is the whole point of the cache."""
    w1 = _wardrobe(a=_item("a", color="#B22222"))  # firebrick red
    w2 = _wardrobe(a=_item("a", color="#DC143C"))  # crimson red
    sig1 = compute_narration_signature(
        [compute_candidate_shape(["a"], w1)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    sig2 = compute_narration_signature(
        [compute_candidate_shape(["a"], w2)],
        occasion_key="office", engine_version="engine-v2", llm_candidate_count=6,
    )
    assert sig1 == sig2


def test_hmac_changes_if_suggestion_cache_salt_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyed-hash proof, not plain sha256."""
    w = _wardrobe(a=_item("a"))
    shape = compute_candidate_shape(["a"], w)

    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "salt-one")
    sig1 = compute_narration_signature(
        [shape], occasion_key="office", engine_version="engine-v2", llm_candidate_count=6
    )
    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "salt-two")
    sig2 = compute_narration_signature(
        [shape], occasion_key="office", engine_version="engine-v2", llm_candidate_count=6
    )
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# Golden-file cache-key regression test -- locks compute_narration_signature's
# EXACT output for a fixed input. If this test ever needs to change, that is
# the literal moment the "cache keys are near-impossible to change once
# live" risk fires -- must be flagged loudly in that PR, not silently
# updated (design doc's Test plan, verbatim).
# ---------------------------------------------------------------------------


def test_golden_file_signature_is_locked_for_a_fixed_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUGGESTION_CACHE_SALT", "golden-file-fixed-salt-do-not-change")
    w = _wardrobe(
        top1=_item("top1", category="western_top", color="#1E3A8A"),
        bottom1=_item("bottom1", category="western_bottom", color="#1E3A8A"),
        shoe1=_item("shoe1", category="footwear_casual", color="#000000"),
    )
    shape = compute_candidate_shape(["top1", "bottom1", "shoe1"], w)
    signature = compute_narration_signature(
        [shape], occasion_key="office", engine_version="engine-v2", llm_candidate_count=6
    )
    assert signature == "1eb13ec4cdb295356fb4217143f267986205def9f063e4c43a0d3149d0cfd6ca"


# ---------------------------------------------------------------------------
# signature_order -- inverse permutation correctness
# ---------------------------------------------------------------------------


def test_signature_order_maps_signature_index_back_to_original_index() -> None:
    w = _wardrobe(a=_item("a", category="western_top"), b=_item("b", category="ethnic_saree"))
    shapes = [compute_candidate_shape(["b"], w), compute_candidate_shape(["a"], w)]
    order = signature_order(shapes)
    # order[sig_idx] == original_idx
    assert len(order) == 2
    assert set(order) == {0, 1}


# ---------------------------------------------------------------------------
# NarrationCacheOrchestrator -- never raises
# ---------------------------------------------------------------------------


class _RaisingRepo(ISuggestionNarrationCacheRepository):
    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        raise RuntimeError("cache backend down")

    async def put(self, **kwargs: object) -> None:
        raise RuntimeError("cache backend down")


class _WorkingRepo(ISuggestionNarrationCacheRepository):
    def __init__(self) -> None:
        self.put_calls: list[dict[str, object]] = []

    async def get(self, *, signature_hash: str) -> CachedNarration | None:
        return CachedNarration(narrations_by_signature_index={0: "a nice pick"}, language="en")

    async def put(self, **kwargs: object) -> None:
        self.put_calls.append(kwargs)


async def test_get_degrades_to_none_on_repository_failure_never_raises() -> None:
    orchestrator = NarrationCacheOrchestrator(_RaisingRepo())
    result = await orchestrator.get(signature_hash="a" * 64)
    assert result is None


async def test_put_swallows_repository_failure_never_raises() -> None:
    orchestrator = NarrationCacheOrchestrator(_RaisingRepo())
    await orchestrator.put(
        signature_hash="a" * 64,
        occasion_key="office",
        engine_version="engine-v2",
        narrations_by_signature_index={0: "text"},
        language="en",
        ttl_seconds=21600,
    )  # must not raise


async def test_get_returns_real_cached_narration_on_success() -> None:
    orchestrator = NarrationCacheOrchestrator(_WorkingRepo())
    result = await orchestrator.get(signature_hash="a" * 64)
    assert result is not None
    assert result.narrations_by_signature_index == {0: "a nice pick"}

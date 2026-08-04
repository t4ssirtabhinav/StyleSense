"""``SuggestionLogService`` -- pure orchestration for SS-033's suggestion
impression & outcome logging substrate (design §5.3).

No I/O of its own beyond delegating to the ``ISuggestionLogRepository``
port. Owns:

- ``ENGINE_VERSION`` -- the single definition of the engine-version string
  written onto every session log (design §4; bumped by whoever changes
  scoring behaviour -- SS-035 owns the tuning dial, see ``BL-114``).
- ``outfit_fingerprint()`` / ``config_snapshot_hash()`` -- the two hashing
  helpers the DB's CHECK constraints and SS-023's "no repeat outfit" AC
  both depend on.
- ``impressions_from_candidates()`` -- maps SS-027's ``ScoredCandidate``
  onto ``SuggestionImpressionLog`` rows, 1-based rank in engine order.
- ``log_suggestion()`` -- the single entry point SS-020 will call.

**Log-and-continue, by construction (design §5.4).** Every public method
here wraps its body in its own ``try/except`` so a mapping bug (e.g. a
malformed candidate) can never propagate into the caller, even though the
repository underneath is independently documented never-raising. No caller
ever *needs* the return value to proceed -- ``log_suggestion`` returning
``None`` means "no outcomes can be attached to this request" (degraded
analytics), never a degraded suggestion.

Not wired into ``backend/services/outfit_suggestion_service.py`` by this
ticket -- that file is explicitly out of scope (``BL-096``'s landmine,
``BL-102``'s precedent). SS-020 does the wiring.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Container, Mapping, Sequence
from typing import Any

from adapters.interfaces import (
    ISuggestionLogRepository,
    SuggestionImpressionLog,
    SuggestionSessionLog,
)
from services.styling_rules_types import ScoredCandidate

logger = logging.getLogger(__name__)

# <engine>-v<major>. No engine-version constant existed anywhere in this
# codebase before this ticket (design §4) -- "rules-v1" describes SS-027's
# rules engine, the only engine that exists. A version that never changes
# is worse than no version at all: it makes two incomparable datasets
# (different scoring behaviour) look comparable. See BL-114.
ENGINE_VERSION = "rules-v1"

# Transcribed verbatim from 013_suggestion_impressions.sql's
# suggestion_sessions_zero_cost_reason_check -- kept in sync manually (no
# single source of truth spans Python and SQL enums in this codebase).
_ZERO_COST_REASONS = frozenset(
    {"cache_hit", "degraded_e0", "rules_only", "budget_denied", "no_provider_call"}
)


def outfit_fingerprint(item_ids: Sequence[str]) -> str:
    """``sha256(":".join(sorted(item_ids)))``, lowercase hex -- order
    independent by construction, so the same three garments always
    fingerprint identically regardless of assembly order (design §3.3).
    Duplicate ids within one candidate are NOT de-duplicated -- a genuine
    duplicate is a bug worth seeing in the data, not one worth hiding in a
    hash."""
    return hashlib.sha256(":".join(sorted(item_ids)).encode()).hexdigest()


def config_snapshot_hash(values: Mapping[str, Any]) -> str:
    """``sha256`` of the canonical (sorted-key, no-whitespace) JSON
    encoding of ``values`` -- stable regardless of dict insertion order.
    Compute this from the ONE ``AppConfigSnapshot`` the request already
    holds (SS-026's "one request, one snapshot" rule) -- never call
    ``.snapshot()`` a second time just to hash it."""
    encoded = json.dumps(dict(values), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def impressions_from_candidates(
    candidates: Sequence[ScoredCandidate],
    *,
    exploration_ranks: Container[int] = (),
) -> list[SuggestionImpressionLog]:
    """1-based ranks in the exact order the engine returned ``candidates``.
    ``rule_scores`` is serialised via ``model_dump()`` (``RuleScore`` is a
    Pydantic model); ``is_exploration`` is set purely by rank membership in
    ``exploration_ranks``."""
    impressions: list[SuggestionImpressionLog] = []
    for rank, candidate in enumerate(candidates, start=1):
        impressions.append(
            SuggestionImpressionLog(
                rank=rank,
                item_ids=list(candidate.item_ids),
                outfit_fingerprint=outfit_fingerprint(candidate.item_ids),
                total_score=candidate.total_score,
                rule_scores=[rule_score.model_dump() for rule_score in candidate.rule_scores],
                gap_flags=list(candidate.gap_flags),
                is_exploration=rank in exploration_ranks,
            )
        )
    return impressions


class SuggestionLogService:
    """Constructor-injected with an ``ISuggestionLogRepository``. Pure
    orchestration -- never talks to Postgres directly (design §5.3)."""

    def __init__(self, repository: ISuggestionLogRepository) -> None:
        self._repository = repository

    async def log_suggestion(
        self,
        *,
        user_id: str,
        occasion: str | None = None,
        weather_data: dict[str, Any] | None = None,
        tier: str | None = None,
        effort_tier: str | None = None,
        config_snapshot: Mapping[str, Any] | None = None,
        candidates: Sequence[ScoredCandidate] = (),
        exploration_ranks: Container[int] = (),
        cache_key: str | None = None,
        request_id: str | None = None,
        latency_ms: int | None = None,
        cost_incurred: bool = True,
        zero_cost_reason: str | None = None,
    ) -> str | None:
        """The single entry point SS-020 will call. Builds the session log
        (including the cost marker pair), maps ``candidates`` to impression
        rows, delegates to ``ISuggestionLogRepository.log_session()``, and
        returns the session id or ``None``. Wrapped in its own
        ``try/except`` so even a mapping bug cannot propagate into the
        caller -- see design §5.4."""
        try:
            if not cost_incurred and zero_cost_reason is None:
                logger.error("suggestion_log_zero_cost_reason_missing", extra={"user_id": user_id})
                return None
            if cost_incurred and zero_cost_reason is not None:
                logger.error(
                    "suggestion_log_zero_cost_reason_unexpected",
                    extra={"user_id": user_id, "zero_cost_reason": zero_cost_reason},
                )
                return None
            if zero_cost_reason is not None and zero_cost_reason not in _ZERO_COST_REASONS:
                logger.error(
                    "suggestion_log_zero_cost_reason_invalid",
                    extra={"user_id": user_id, "zero_cost_reason": zero_cost_reason},
                )
                return None

            session = SuggestionSessionLog(
                user_id=user_id,
                occasion=occasion,
                weather_data=weather_data,
                tier=tier,
                effort_tier=effort_tier,
                engine_version=ENGINE_VERSION,
                config_snapshot_hash=(
                    config_snapshot_hash(config_snapshot) if config_snapshot is not None else None
                ),
                candidate_count=len(candidates),
                cache_key=cache_key,
                request_id=request_id,
                latency_ms=latency_ms,
                cost_incurred=cost_incurred,
                zero_cost_reason=zero_cost_reason,
            )
            impressions = impressions_from_candidates(
                candidates, exploration_ranks=exploration_ranks
            )
            return await self._repository.log_session(session, impressions)
        except Exception as exc:  # log-and-continue -- design §5.4 layer 2/3
            logger.error("suggestion_log_failed", extra={"user_id": user_id, "error": str(exc)})
            return None

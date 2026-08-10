"""``ConfigSpec``s for SS-028's three ``app_config`` keys (design §4).

Per SS-026's own guidance (design §10): a domain ticket adds its own specs
module near its own service rather than growing ``app_config_specs.py``
indefinitely.

**Model ID strings -- ``[VERIFIED 2026-07-30]`` against the real
``GEMINI_API_KEY``/``ANTHROPIC_API_KEY`` and the actually-installed
``google-genai==2.14.0``/``anthropic==0.116.0`` SDKs.** See
``docs/worklog/SS-028.md``'s Developer entry for the exact commands/output;
summarized here since these constants are the thing every reader will want
to double-check:

- ``EVERYDAY_MODEL_ID = "gemini-3.1-flash-lite"`` -- **promoted from
  ``gemini-2.5-flash-lite`` on 2026-08-10 (user-directed live fix)**.
  ``gemini-2.5-flash-lite`` is present in this account's
  ``client.aio.models.list()``, but a live ``generate_content`` call
  against it returns ``google.genai.errors.ClientError(code=404, "... no
  longer available to new users ...")`` for THIS account/key -- it was
  shipped anyway by SS-028 per the user's B1 decision at the time
  (``docs/worklog/SS-028.md``'s "Orchestrator -- 2026-07-30" entry), on the
  premise that ``EVERYDAY_FALLBACK_MODEL_ID``'s in-tier retry hop inside
  ``GeminiStylingAdapter`` would cover the gap. The live ``app_config``
  row for ``ai_styling_routing_table`` was updated the same day (2026-08-10,
  ``UPDATE ... jsonb_set(value, '{default,model}', ...)``, no
  redeploy/restart per SS-026's live-reload design) to route the
  "everyday" default straight to the already-verified-working model
  instead of paying for a 404-then-retry round trip on every call. This
  constant is updated to match so the config-unreachable degrade path
  doesn't silently revert to the broken model.
- ``EVERYDAY_FALLBACK_MODEL_ID = "gemini-2.5-flash-lite"`` -- kept as the
  in-tier retry hop for symmetry with the pre-2026-08-10 shape, even though
  it is the model now known to 404 for this account -- if this account's
  access to it is ever restored, the fallback slot is still meaningful;
  until then it will simply never succeed as a fallback. Not removed
  outright since ``GeminiStylingAdapter``'s retry-hop mechanism itself is
  unrelated to which two model IDs occupy the two slots.
- ``HIGH_STAKES_MODEL_ID = "claude-sonnet-5"`` -- present in
  ``anthropic.types.model_param.ModelParam``'s ``Literal[...]`` (the
  installed SDK's own accepted-model-ID list) AND live-verified callable
  via ``client.messages.create(..., tool_choice={"type": "tool", ...})``
  against the real key, returning a valid ``tool_use`` block. This is the
  literal API ID matching the raw ticket's prose "Claude Sonnet 5" -- not a
  guess, a live-checked match.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, RootModel, model_validator

from services.app_config import ConfigSpec

EVERYDAY_MODEL_ID = "gemini-3.1-flash-lite"
EVERYDAY_FALLBACK_MODEL_ID = "gemini-2.5-flash-lite"
HIGH_STAKES_MODEL_ID = "claude-sonnet-5"


# ---------------------------------------------------------------------------
# ai_styling_routing_table
# ---------------------------------------------------------------------------


class Route(BaseModel):
    provider: str
    model: str
    cost_class: Literal["everyday", "high_stakes"]
    reason: str


class RoutingRule(BaseModel):
    # Deliberately a raw dict, not a closed Pydantic model -- an unknown
    # field inside `when` must make only THIS rule inert (skipped, logged
    # once at WARNING), never fail the whole table's validation (design
    # §4.1). `styling_router.resolve_route()` owns interpreting this dict.
    when: dict[str, object] = Field(default_factory=dict)
    route: Route


class RoutingTableConfig(BaseModel):
    # `version` is informational only -- logged with each decision so a bad
    # table can be traced to a config edit. Never branched on in code
    # (design §4.1's explicit instruction).
    version: int = 1
    default: Route
    rules: list[RoutingRule] = Field(default_factory=list)
    failover: dict[str, list[str]] = Field(default_factory=dict)


DEFAULT_ROUTING_TABLE = RoutingTableConfig(
    version=1,
    default=Route(
        provider="gemini",
        model=EVERYDAY_MODEL_ID,
        cost_class="everyday",
        reason="default_everyday",
    ),
    rules=[
        RoutingRule(
            when={"tier": ["atelier"]},
            route=Route(
                provider="claude",
                model=HIGH_STAKES_MODEL_ID,
                cost_class="high_stakes",
                reason="tier_atelier",
            ),
        ),
        RoutingRule(
            when={"is_first_suggestion": True},
            route=Route(
                provider="claude",
                model=HIGH_STAKES_MODEL_ID,
                cost_class="high_stakes",
                reason="first_ever_suggestion",
            ),
        ),
        RoutingRule(
            when={"occasion": ["wedding_guest"]},
            route=Route(
                provider="claude",
                model=HIGH_STAKES_MODEL_ID,
                cost_class="high_stakes",
                reason="high_stakes_occasion",
            ),
        ),
        RoutingRule(
            when={"occasion_kind": ["ceremony", "festival"]},
            route=Route(
                provider="claude",
                model=HIGH_STAKES_MODEL_ID,
                cost_class="high_stakes",
                reason="high_stakes_occasion_kind",
            ),
        ),
    ],
    failover={"gemini": ["claude"], "claude": ["gemini"]},
)

AI_STYLING_ROUTING_TABLE_SPEC: ConfigSpec[RoutingTableConfig] = ConfigSpec(
    key="ai_styling_routing_table",
    model=RoutingTableConfig,
    default=DEFAULT_ROUTING_TABLE,
)


# ---------------------------------------------------------------------------
# ai_provider_quota
# ---------------------------------------------------------------------------


class ProviderQuotaEntry(BaseModel):
    rpm: int = Field(gt=0)
    tpm: int = Field(gt=0)


class ProviderQuotaConfig(RootModel[dict[str, ProviderQuotaEntry]]):
    """A dict of provider -> ceiling. An unknown provider KEY (one
    ``ProviderQuotaTracker``/``StylingRouter`` never look up) is simply
    ignored by callers, not rejected here -- this model only enforces that
    whatever entries ARE present have a valid (rpm, tpm) shape. A provider
    absent from this dict entirely is unlimited (design §4.2)."""


DEFAULT_PROVIDER_QUOTA = ProviderQuotaConfig(
    root={
        "gemini": ProviderQuotaEntry(rpm=15, tpm=500000),
        "claude": ProviderQuotaEntry(rpm=50, tpm=30000),
    }
)

AI_PROVIDER_QUOTA_SPEC: ConfigSpec[ProviderQuotaConfig] = ConfigSpec(
    key="ai_provider_quota",
    model=ProviderQuotaConfig,
    default=DEFAULT_PROVIDER_QUOTA,
)


# ---------------------------------------------------------------------------
# ai_router_policy
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        hi = lo
    return max(lo, min(hi, value))


class RouterPolicyConfig(BaseModel):
    attempt_timeout_seconds: float = 6.0
    total_deadline_seconds: float = 12.0
    parse_retry_attempts: int = 1
    expensive_share_alert_threshold: float = 0.30
    alert_min_sample: int = 20
    alert_cooldown_seconds: int = 3600
    provider_outage_alert_seconds: int = 900

    @model_validator(mode="after")
    def _clamp_all_fields(self) -> RouterPolicyConfig:
        """Every field clamped exactly per design §4.3 -- a shape-valid but
        degenerate number must never disable the router. Clamped in
        dependency order: total_deadline_seconds is clamped relative to
        the ALREADY-clamped attempt_timeout_seconds, so a config value
        smaller than the (clamped) per-attempt timeout is clamped UP
        rather than producing a zero-attempt router."""
        self.attempt_timeout_seconds = _clamp(self.attempt_timeout_seconds, 1.0, 60.0)
        self.total_deadline_seconds = _clamp(
            self.total_deadline_seconds, self.attempt_timeout_seconds, 120.0
        )
        self.parse_retry_attempts = int(_clamp(self.parse_retry_attempts, 0, 2))
        self.expensive_share_alert_threshold = _clamp(
            self.expensive_share_alert_threshold, 0.0, 1.0
        )
        self.alert_min_sample = int(_clamp(self.alert_min_sample, 1, 10000))
        self.alert_cooldown_seconds = int(_clamp(self.alert_cooldown_seconds, 60, 86400))
        self.provider_outage_alert_seconds = int(
            _clamp(self.provider_outage_alert_seconds, 60, 86400)
        )
        return self


AI_ROUTER_POLICY_SPEC: ConfigSpec[RouterPolicyConfig] = ConfigSpec(
    key="ai_router_policy",
    model=RouterPolicyConfig,
    default=RouterPolicyConfig(),
)

"""Pydantic schemas for the hello-gateway steward's output.

The Gateway Steward's read-only product is a **routing-plane posture report**: it
reads the LiteLLM proxy's configured routes, their per-route budget caps, and the
health of each route's upstream, then reports on routing/cost governance. The
schema is intentionally *narrow*: in the read-only iteration it cannot represent
a proposed write (a budget change). ``requires_hitl`` is reserved for future
iterations and MUST validate to False here — the third no-write defence layer,
mirroring the Inference, Pipeline, Quality, and SRE stewards.

``proposed_adjustment`` is a *sentence of advice*, not an action: it is the
steward telling a human what it would recommend, never a machine instruction.
The gated write (Iteration 2) is a separate, human-approved path.
"""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION: str = "1.0.0"

Posture = Literal["healthy", "degraded", "misconfigured"]


class GatewayObservation(BaseModel):
    """One read-only assessment of the LLM routing plane (LiteLLM proxy).

    Future schema versions will add ``proposed_budget`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so the
    LLM has no language to express a plane write. ``proposed_adjustment`` remains
    advice-only.
    """

    routes_observed: int = Field(
        ..., ge=0, le=10000, description="Number of configured LiteLLM routes (model groups)."
    )
    routes_healthy: int = Field(
        ..., ge=0, le=10000, description="Routes whose upstream deployment is serving."
    )
    routes_unhealthy: int = Field(
        ..., ge=0, le=10000, description="Routes whose upstream deployment is NOT serving."
    )
    min_budget_cap: float | None = Field(
        None,
        ge=0.0,
        description="Smallest per-route budget cap observed (USD), or null if none configured.",
    )
    max_budget_cap: float | None = Field(
        None,
        ge=0.0,
        description="Largest per-route budget cap observed (USD), or null if none configured.",
    )
    budget_policy_concern: bool = Field(
        False,
        description="Read-only signal: True if a route's budget/health posture looks misconfigured.",
    )
    posture: Posture = Field(
        "healthy",
        description="Overall routing-plane posture: healthy | degraded | misconfigured.",
    )
    suspected_issue: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="One-line hypothesis for the dominant signal (or 'none — routing plane healthy').",
    )
    proposed_adjustment: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="Advice-only recommendation for a human (NOT an action), e.g. 'consider raising budget'.",
    )
    summary: str = Field(
        ...,
        min_length=20,
        max_length=1000,
        description="2-5 sentence plain-English routing/cost posture narrative.",
    )
    requires_hitl: bool = Field(
        False,
        description="Reserved for future iterations. MUST be False in v1.0.0.",
    )

    @model_validator(mode="after")
    def _no_write_intent(self) -> Self:
        if self.requires_hitl:
            raise ValueError(
                "requires_hitl=True is not allowed in the read-only iteration. "
                "If you see this, the third-layer no-write defence has fired."
            )
        # A 'misconfigured' posture with no concern flagged is internally
        # inconsistent — fail closed so the report cannot mislead.
        if self.posture == "misconfigured" and not self.budget_policy_concern:
            raise ValueError("posture='misconfigured' requires budget_policy_concern=True.")
        # Health accounting must be self-consistent.
        if self.routes_healthy + self.routes_unhealthy > self.routes_observed:
            raise ValueError("routes_healthy + routes_unhealthy cannot exceed routes_observed.")
        return self

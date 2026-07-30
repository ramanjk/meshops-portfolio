"""Pydantic schemas for the hello-sre steward's output.

The SRE steward's read-only product is an **incident correlation report**: it
joins Prometheus metrics, AKS cluster state, and Langfuse LLM traces into one
timeline + hypothesis + proposed remediation. The schema is intentionally
*narrow*: in the read-only iteration it cannot represent a proposed write
action (a Deployment scale). ``requires_hitl`` is reserved for future iterations
and MUST validate to False here — the third no-write defence layer, mirroring
the Inference, Pipeline, and Quality stewards.

``proposed_remediation`` is a *sentence of advice*, not an action: it is the
steward telling a human what it would recommend, never a machine instruction.
The gated write (Iteration 2) is a separate, human-approved path.
"""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION: str = "1.0.0"

Severity = Literal["none", "low", "medium", "high"]


class IncidentObservation(BaseModel):
    """One read-only cross-substrate correlation of platform health.

    Future schema versions will add ``proposed_scale`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so the
    LLM has no language to express a cluster write (the SRE steward's eventual
    gated action). ``proposed_remediation`` remains advice-only.
    """

    services_observed: int = Field(
        ..., ge=0, le=100000, description="Number of distinct services/workloads correlated."
    )
    alerts_firing: int = Field(
        ..., ge=0, le=100000, description="Count of firing Prometheus alerts / breached signals."
    )
    gpu_util_percent: float | None = Field(
        None,
        ge=0.0,
        le=100.0,
        description="GPU utilisation percent from Prometheus, or null if no GPU/metric observed.",
    )
    error_rate: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Observed request/inference error rate in [0,1], or null if not measurable.",
    )
    traces_observed: int = Field(
        ..., ge=0, le=100000, description="Number of recent Langfuse LLM traces correlated."
    )
    incident_suspected: bool = Field(
        False,
        description="Read-only signal: True if the correlated signals suggest an active incident.",
    )
    severity: Severity = Field(
        "none",
        description="Overall severity of the correlated picture: none | low | medium | high.",
    )
    suspected_root_cause: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="One-line hypothesis for the dominant signal (or 'none — platform healthy').",
    )
    proposed_remediation: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="Advice-only recommendation for a human (NOT an action). e.g. 'consider scaling X'.",
    )
    summary: str = Field(
        ...,
        min_length=20,
        max_length=1000,
        description="2-5 sentence plain-English incident timeline / health narrative across substrates.",
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
        # A high-severity picture with no incident flagged is internally
        # inconsistent — fail closed so the report cannot mislead.
        if self.severity == "high" and not self.incident_suspected:
            raise ValueError("severity='high' requires incident_suspected=True.")
        return self

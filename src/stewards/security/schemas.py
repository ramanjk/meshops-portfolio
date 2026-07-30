"""Pydantic schemas for the hello-security steward's output.

The Security Steward's read-only product is a **threat-classification posture
report**: it reads the open HITL proposal queue (peer-steward proposal PRs and
other open PRs) and classifies each input against a prompt-injection /
confused-deputy / data-poisoning rubric, then reports the mesh's input-trust
posture. The schema is intentionally *narrow*: in the read-only iteration it
cannot represent a proposed write (a quarantine). ``requires_hitl`` is reserved
for future iterations and MUST validate to False here — the third no-write
defence layer, mirroring the Inference, Pipeline, Quality, SRE, and Gateway
stewards.

``proposed_action`` is a *sentence of advice*, not an action: it is the steward
telling a human what it would recommend (e.g. "consider quarantining PR #12"),
never a machine instruction. Classification is read-only; the gated quarantine
(Iteration 2) is a separate, human-approved path.
"""
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION: str = "1.0.0"

Threat = Literal["none", "prompt_injection", "confused_deputy", "data_poisoning", "other"]
Risk = Literal["none", "low", "medium", "high", "critical"]


class SecurityObservation(BaseModel):
    """One read-only classification of the HITL proposal queue (open PRs).

    Future schema versions will add ``proposed_quarantine`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so the
    LLM has no language to express a quarantine write. ``proposed_action`` remains
    advice-only.
    """

    inputs_observed: int = Field(
        ..., ge=0, le=10000, description="Number of open PRs / proposals classified this cycle."
    )
    benign_count: int = Field(
        ..., ge=0, le=10000, description="Inputs judged benign (no rubric hit)."
    )
    suspicious_count: int = Field(
        ..., ge=0, le=10000, description="Inputs with a weak/ambiguous rubric signal."
    )
    malicious_count: int = Field(
        ..., ge=0, le=10000, description="Inputs with a strong rubric hit (likely attack)."
    )
    dominant_threat: Threat = Field(
        "none",
        description="Dominant threat class across the queue, or 'none' if all benign.",
    )
    highest_risk: Risk = Field(
        "none",
        description="Highest per-input risk rating observed: none|low|medium|high|critical.",
    )
    threat_suspected: bool = Field(
        False,
        description="Read-only signal: True if any input looks suspicious or malicious.",
    )
    suspected_issue: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="One-line description of the dominant finding (or 'none — queue looks clean').",
    )
    proposed_action: str = Field(
        ...,
        min_length=3,
        max_length=600,
        description="Advice-only recommendation for a human (NOT an action), e.g. 'consider quarantine'.",
    )
    summary: str = Field(
        ...,
        min_length=20,
        max_length=1000,
        description="2-5 sentence plain-English input-trust posture narrative.",
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
        # A high/critical risk with nothing flagged as suspected is internally
        # inconsistent — fail closed so the report cannot mislead.
        if self.highest_risk in ("high", "critical") and not self.threat_suspected:
            raise ValueError("highest_risk high|critical requires threat_suspected=True.")
        # A non-'none' dominant threat implies at least a suspicion.
        if self.dominant_threat != "none" and not self.threat_suspected:
            raise ValueError("dominant_threat other than 'none' requires threat_suspected=True.")
        # Classification accounting must be self-consistent.
        if self.benign_count + self.suspicious_count + self.malicious_count > self.inputs_observed:
            raise ValueError(
                "benign_count + suspicious_count + malicious_count cannot exceed inputs_observed."
            )
        return self

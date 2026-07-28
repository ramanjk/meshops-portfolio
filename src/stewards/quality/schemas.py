"""Pydantic schemas for the hello-quality steward's output.

The schema is intentionally *narrow*: it cannot represent a proposed write
action (opening a prompt-version PR) this iteration. The ``requires_hitl`` field
is reserved for future iterations and MUST validate to False here (the third
no-write defence layer, mirroring the Inference and Pipeline stewards).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

SCHEMA_VERSION: str = "1.0.0"


class QualityObservation(BaseModel):
    """One read-only observation of LLM quality signals in Langfuse.

    Future schema versions will add ``proposed_prompt_pr`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so
    the LLM has no language to express a repository write (the Quality steward's
    eventual gated action).
    """

    traces_observed: int = Field(
        ..., ge=0, le=100000, description="Number of recent traces sampled from Langfuse."
    )
    scored_traces: int = Field(
        ...,
        ge=0,
        le=100000,
        description="How many of the sampled traces carry at least one evaluation score.",
    )
    total_scores: int = Field(
        ..., ge=0, le=100000, description="Total number of evaluation scores observed."
    )
    mean_quality_score: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Mean of numeric evaluation scores in [0,1], or null if none were observed.",
    )
    drift_suspected: bool = Field(
        False,
        description="Read-only signal: True if the sampled scores suggest a quality regression/drift.",
    )
    summary: str = Field(
        ...,
        min_length=20,
        max_length=800,
        description="2-4 sentence plain-English, read-only status of eval/quality health for the sampled "
        "traces.",
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
        return self

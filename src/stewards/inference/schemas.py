"""Pydantic schemas for the hello-inference steward's output.

The schema is intentionally *narrow*: it cannot represent a proposed write
action this iteration. The `requires_hitl` field is reserved for future
iterations and MUST validate to False here (the third no-write defence layer).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self


SCHEMA_VERSION: str = "1.0.0"


class InferenceObservation(BaseModel):
    """One read-only observation of a KAITO Workspace.

    Future schema versions will add ``proposed_actions`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so
    the LLM has no language to express a write.
    """

    workspace_name: str = Field(..., description="Name of the KAITO Workspace observed.")
    replica_count: int = Field(..., ge=0, le=100)
    gpu_util_percent: float = Field(..., ge=0.0, le=100.0)
    summary: str = Field(..., min_length=20, max_length=800)
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

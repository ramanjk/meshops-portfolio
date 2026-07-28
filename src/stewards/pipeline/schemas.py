"""Pydantic schemas for the hello-pipeline steward's output.

The schema is intentionally *narrow*: it cannot represent a proposed write
action (a registry promotion) this iteration. The ``requires_hitl`` field is
reserved for future iterations and MUST validate to False here (the third
no-write defence layer, mirroring the Inference steward).
"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator
from typing_extensions import Self

SCHEMA_VERSION: str = "1.0.0"


class PipelineObservation(BaseModel):
    """One read-only observation of an MLflow registered model.

    Future schema versions will add ``proposed_promotion`` and ``hitl_envelope``;
    this read-only iteration (Iteration 1) deliberately omits those fields so
    the LLM has no language to express a registry write.
    """

    registered_model_name: str = Field(..., description="Name of the MLflow registered model observed.")
    total_versions: int = Field(..., ge=0, le=10000, description="Count of model versions.")
    staging_versions: int = Field(..., ge=0, le=10000, description="Versions currently in the Staging stage.")
    production_versions: int = Field(
        ..., ge=0, le=10000, description="Versions currently in the Production stage."
    )
    latest_version: int = Field(..., ge=0, le=100000, description="Highest version number registered.")
    summary: str = Field(
        ...,
        min_length=20,
        max_length=800,
        description="2-4 sentence plain-English, read-only status of the registry for this model.",
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

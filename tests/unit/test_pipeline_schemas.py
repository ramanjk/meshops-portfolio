"""Unit tests for the Pipeline steward's read-only schema and the third no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.pipeline.schemas import SCHEMA_VERSION, PipelineObservation


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = {
        "registered_model_name": "phi-4-mini-meshops",
        "total_versions": 3,
        "staging_versions": 1,
        "production_versions": 1,
        "latest_version": 3,
        "summary": "Model has three versions; v2 in Production and v3 in Staging awaiting validation.",
        "requires_hitl": False,
    }
    obs = PipelineObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    payload = {
        "registered_model_name": "phi-4-mini-meshops",
        "total_versions": 3,
        "staging_versions": 1,
        "production_versions": 1,
        "latest_version": 3,
        "summary": "Propose promoting v3 to Production because staging validation looks complete.",
        "requires_hitl": True,
    }
    with pytest.raises(ValidationError):
        PipelineObservation.model_validate(payload)


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_promotion)."""
    payload = {
        "registered_model_name": "phi-4-mini-meshops",
        "total_versions": 0,
        "staging_versions": 0,
        "production_versions": 0,
        "latest_version": 0,
        "summary": "Stub summary that is long enough to pass min_length validation.",
        "requires_hitl": False,
        "proposed_promotion": {"version": 3, "to_stage": "Production"},
    }
    obs = PipelineObservation.model_validate(payload)
    dumped = obs.model_dump()
    assert "proposed_promotion" not in dumped

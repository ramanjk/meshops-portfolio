"""Unit tests for the Inference steward's read-only schema and the third no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.inference.schemas import SCHEMA_VERSION, InferenceObservation


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = {
        "workspace_name": "lab-phi-4-mini-eus2-01",
        "replica_count": 1,
        "gpu_util_percent": 12.5,
        "summary": "Workspace healthy at 1 replica with GPU utilisation about 12 percent.",
        "requires_hitl": False,
    }
    obs = InferenceObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    payload = {
        "workspace_name": "lab-phi-4-mini-eus2-01",
        "replica_count": 1,
        "gpu_util_percent": 12.5,
        "summary": "Propose scaling +1 because GPU is busy enough to warrant it.",
        "requires_hitl": True,
    }
    with pytest.raises(ValidationError):
        InferenceObservation.model_validate(payload)


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_actions)."""
    payload = {
        "workspace_name": "x" * 5,
        "replica_count": 0,
        "gpu_util_percent": 0.0,
        "summary": "Stub summary that is long enough to pass min_length validation.",
        "requires_hitl": False,
        "proposed_actions": ["kubectl scale --replicas=2"],
    }
    obs = InferenceObservation.model_validate(payload)
    dumped = obs.model_dump()
    assert "proposed_actions" not in dumped

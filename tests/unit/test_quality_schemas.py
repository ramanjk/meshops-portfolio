"""Unit tests for the Quality steward's read-only schema and the third no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.quality.schemas import SCHEMA_VERSION, QualityObservation


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = {
        "traces_observed": 50,
        "scored_traces": 40,
        "total_scores": 45,
        "mean_quality_score": 0.87,
        "drift_suspected": False,
        "summary": "Sampled 50 traces; 40 carry scores averaging 0.87 faithfulness — quality looks healthy.",
        "requires_hitl": False,
    }
    obs = QualityObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_mean_score_nullable_when_no_scores() -> None:
    payload = {
        "traces_observed": 12,
        "scored_traces": 0,
        "total_scores": 0,
        "mean_quality_score": None,
        "drift_suspected": False,
        "summary": "Sampled 12 traces but none carry evaluation scores yet, so no quality signal is available.",
        "requires_hitl": False,
    }
    obs = QualityObservation.model_validate(payload)
    assert obs.mean_quality_score is None


def test_mean_score_out_of_range_rejected() -> None:
    payload = {
        "traces_observed": 5,
        "scored_traces": 5,
        "total_scores": 5,
        "mean_quality_score": 1.5,
        "drift_suspected": False,
        "summary": "This summary is long enough to satisfy the min_length validation constraint.",
        "requires_hitl": False,
    }
    with pytest.raises(ValidationError):
        QualityObservation.model_validate(payload)


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    payload = {
        "traces_observed": 50,
        "scored_traces": 40,
        "total_scores": 45,
        "mean_quality_score": 0.61,
        "drift_suspected": True,
        "summary": "Scores dropped to 0.61; propose opening a prompt-fix PR to recover faithfulness.",
        "requires_hitl": True,
    }
    with pytest.raises(ValidationError):
        QualityObservation.model_validate(payload)


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_prompt_pr)."""
    payload = {
        "traces_observed": 0,
        "scored_traces": 0,
        "total_scores": 0,
        "mean_quality_score": None,
        "drift_suspected": False,
        "summary": "Stub summary that is long enough to pass min_length validation.",
        "requires_hitl": False,
        "proposed_prompt_pr": {"repo": "meshops", "branch": "fix-prompt"},
    }
    obs = QualityObservation.model_validate(payload)
    dumped = obs.model_dump()
    assert "proposed_prompt_pr" not in dumped

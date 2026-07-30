"""Unit tests for the Security steward's read-only schema and no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.security.schemas import SCHEMA_VERSION, SecurityObservation


def _base(**over: object) -> dict:
    payload = {
        "inputs_observed": 3,
        "benign_count": 3,
        "suspicious_count": 0,
        "malicious_count": 0,
        "dominant_threat": "none",
        "highest_risk": "none",
        "threat_suspected": False,
        "suspected_issue": "none — queue looks clean",
        "proposed_action": "no action needed; continue monitoring the queue",
        "summary": "Three open proposals were classified; all look benign with no rubric hits.",
        "requires_hitl": False,
    }
    payload.update(over)
    return payload


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = _base()
    obs = SecurityObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_negative_count_rejected() -> None:
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(_base(malicious_count=-1))


def test_bad_threat_rejected() -> None:
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(_base(dominant_threat="ransomware"))


def test_bad_risk_rejected() -> None:
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(_base(highest_risk="apocalyptic"))


def test_dominant_threat_requires_suspicion() -> None:
    """dominant_threat != none with threat_suspected=False is inconsistent."""
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(
            _base(dominant_threat="prompt_injection", threat_suspected=False)
        )


def test_high_risk_requires_suspicion() -> None:
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(
            _base(highest_risk="critical", threat_suspected=False)
        )


def test_malicious_finding_ok() -> None:
    obs = SecurityObservation.model_validate(
        _base(
            inputs_observed=2,
            benign_count=1,
            suspicious_count=0,
            malicious_count=1,
            dominant_threat="prompt_injection",
            highest_risk="high",
            threat_suspected=True,
            suspected_issue="PR #9 body contains an 'ignore your instructions' payload",
            proposed_action="consider quarantining PR #9",
        )
    )
    assert obs.dominant_threat == "prompt_injection"
    assert obs.highest_risk == "high"


def test_classification_accounting_must_be_consistent() -> None:
    """benign + suspicious + malicious cannot exceed inputs_observed."""
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(
            _base(inputs_observed=2, benign_count=2, suspicious_count=1, malicious_count=0)
        )


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    with pytest.raises(ValidationError):
        SecurityObservation.model_validate(_base(requires_hitl=True))


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_quarantine)."""
    payload = _base(proposed_quarantine={"pr_number": 9, "label": "quarantined"})
    obs = SecurityObservation.model_validate(payload)
    assert "proposed_quarantine" not in obs.model_dump()

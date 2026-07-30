"""Unit tests for the SRE steward's read-only schema and the third no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.sre.schemas import SCHEMA_VERSION, IncidentObservation


def _base(**over: object) -> dict:
    payload = {
        "services_observed": 6,
        "alerts_firing": 0,
        "gpu_util_percent": 42.5,
        "error_rate": 0.0,
        "traces_observed": 20,
        "incident_suspected": False,
        "severity": "none",
        "suspected_root_cause": "none — platform healthy",
        "proposed_remediation": "no action needed; continue monitoring",
        "summary": "Metrics, cluster state, and traces all nominal across the platform right now.",
        "requires_hitl": False,
    }
    payload.update(over)
    return payload


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = _base()
    obs = IncidentObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_nullable_metrics() -> None:
    obs = IncidentObservation.model_validate(_base(gpu_util_percent=None, error_rate=None))
    assert obs.gpu_util_percent is None
    assert obs.error_rate is None


def test_gpu_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        IncidentObservation.model_validate(_base(gpu_util_percent=150.0))


def test_bad_severity_rejected() -> None:
    with pytest.raises(ValidationError):
        IncidentObservation.model_validate(_base(severity="critical"))


def test_high_severity_requires_incident() -> None:
    """severity='high' with incident_suspected=False is internally inconsistent."""
    with pytest.raises(ValidationError):
        IncidentObservation.model_validate(
            _base(severity="high", incident_suspected=False)
        )


def test_high_severity_with_incident_ok() -> None:
    obs = IncidentObservation.model_validate(
        _base(
            severity="high",
            incident_suspected=True,
            alerts_firing=3,
            suspected_root_cause="GPU saturation on the model server node",
            proposed_remediation="consider scaling the demo workload",
        )
    )
    assert obs.severity == "high"


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    with pytest.raises(ValidationError):
        IncidentObservation.model_validate(_base(requires_hitl=True))


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_scale)."""
    payload = _base(proposed_scale={"deployment": "demo-web", "replicas": 5})
    obs = IncidentObservation.model_validate(payload)
    assert "proposed_scale" not in obs.model_dump()

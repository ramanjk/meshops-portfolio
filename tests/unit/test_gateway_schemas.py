"""Unit tests for the Gateway steward's read-only schema and no-write defence layer."""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.gateway.schemas import SCHEMA_VERSION, GatewayObservation


def _base(**over: object) -> dict:
    payload = {
        "routes_observed": 2,
        "routes_healthy": 2,
        "routes_unhealthy": 0,
        "min_budget_cap": 5.0,
        "max_budget_cap": 50.0,
        "budget_policy_concern": False,
        "posture": "healthy",
        "suspected_issue": "none — routing plane healthy",
        "proposed_adjustment": "no change needed; budgets and upstreams look sound",
        "summary": "Two LiteLLM routes over gpt-4.1 are healthy with budget caps of $5 and $50.",
        "requires_hitl": False,
    }
    payload.update(over)
    return payload


def test_schema_version_pinned() -> None:
    assert SCHEMA_VERSION == "1.0.0"


def test_valid_observation_round_trips() -> None:
    payload = _base()
    obs = GatewayObservation.model_validate(payload)
    assert json.loads(obs.model_dump_json()) == payload


def test_nullable_budgets() -> None:
    obs = GatewayObservation.model_validate(_base(min_budget_cap=None, max_budget_cap=None))
    assert obs.min_budget_cap is None
    assert obs.max_budget_cap is None


def test_negative_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        GatewayObservation.model_validate(_base(min_budget_cap=-1.0))


def test_bad_posture_rejected() -> None:
    with pytest.raises(ValidationError):
        GatewayObservation.model_validate(_base(posture="on-fire"))


def test_misconfigured_requires_concern() -> None:
    """posture='misconfigured' with budget_policy_concern=False is inconsistent."""
    with pytest.raises(ValidationError):
        GatewayObservation.model_validate(
            _base(posture="misconfigured", budget_policy_concern=False)
        )


def test_misconfigured_with_concern_ok() -> None:
    obs = GatewayObservation.model_validate(
        _base(
            posture="misconfigured",
            budget_policy_concern=True,
            suspected_issue="chat-economy budget cap of $0 will starve the lane",
            proposed_adjustment="consider raising chat-economy budget",
        )
    )
    assert obs.posture == "misconfigured"


def test_health_accounting_must_be_consistent() -> None:
    """healthy + unhealthy cannot exceed observed."""
    with pytest.raises(ValidationError):
        GatewayObservation.model_validate(
            _base(routes_observed=2, routes_healthy=2, routes_unhealthy=1)
        )


def test_requires_hitl_true_is_rejected() -> None:
    """Third-layer defence: schema must refuse a write intent in v1.0."""
    with pytest.raises(ValidationError):
        GatewayObservation.model_validate(_base(requires_hitl=True))


def test_no_extra_fields() -> None:
    """Pydantic must drop smuggled fields (e.g., proposed_budget)."""
    payload = _base(proposed_budget={"route": "chat-economy", "budget": 20})
    obs = GatewayObservation.model_validate(payload)
    assert "proposed_budget" not in obs.model_dump()

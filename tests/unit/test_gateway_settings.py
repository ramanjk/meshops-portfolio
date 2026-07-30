"""Unit tests for hello-gateway env-var loading and required-field enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.gateway.settings import Settings

REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
    "LANGFUSE_PUBLIC_KEY": "pk-x",
    "LANGFUSE_SECRET_KEY": "sk-x",
    "LITELLM_MASTER_KEY": "sk-master-x",
}


def test_settings_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    assert s.langfuse_host.endswith(":3000")
    assert s.litellm_base_url.endswith(":4000")
    assert s.otel_prometheus_port == 9464
    assert s.run_interval_seconds == 0
    # Write is off by default -> read-only steward.
    assert s.write_enabled is False
    assert s.budget_namespace == "meshops-workloads"
    assert s.budget_configmap == "litellm-config"
    assert s.budget_deployment == "litellm"
    assert s.budget_max == 1000.0


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_allowed_route_set_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("BUDGET_ALLOWED_ROUTES", "chat-premium, chat-economy ,, chat-batch")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_route_set() == {"chat-premium", "chat-economy", "chat-batch"}


def test_empty_allowlist_is_unrestricted(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("BUDGET_ALLOWED_ROUTES", raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_route_set() == set()

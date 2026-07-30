"""Unit tests for hello-sre env-var loading and required-field enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.sre.settings import Settings

REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
    "LANGFUSE_PUBLIC_KEY": "pk-x",
    "LANGFUSE_SECRET_KEY": "sk-x",
    "AKS_RESOURCE_ID": "/subscriptions/x/managedClusters/aks-meshops-lab",
    "AZURE_MONITOR_WORKSPACE_QUERY_URL": "https://x.southcentralus.prometheus.monitor.azure.com",
}


def test_settings_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    assert s.langfuse_host.endswith(":3000")
    assert s.trace_sample_limit == 50
    assert s.otel_prometheus_port == 9464
    assert s.run_interval_seconds == 0
    # Read tool stays read-only; the gated scale is a separate kubectl path.
    assert s.aks_mcp_access_level == "readonly"
    # Write is off by default -> read-only steward.
    assert s.write_enabled is False
    assert s.scale_namespace == "meshops-workloads"
    assert s.scale_max_replicas == 10


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_allowed_deployment_set_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("SCALE_ALLOWED_DEPLOYMENTS", "demo-web, api ,, worker")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_deployment_set() == {"demo-web", "api", "worker"}


def test_empty_allowlist_is_unrestricted(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("SCALE_ALLOWED_DEPLOYMENTS", raising=False)
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_deployment_set() == set()

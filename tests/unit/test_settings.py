"""Unit tests for env-var loading and required-field enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.inference.settings import Settings


REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
    "LANGFUSE_PUBLIC_KEY": "pk-x",
    "LANGFUSE_SECRET_KEY": "sk-x",
    "AKS_RESOURCE_ID": "/subscriptions/0/resourceGroups/r/providers/Microsoft.ContainerService/managedClusters/c",
    "AZURE_MONITOR_WORKSPACE_QUERY_URL": "https://x.prometheus.monitor.azure.com",
}


def test_settings_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    assert s.aks_mcp_access_level == "readonly"
    assert s.workspace_name == "lab-phi-4-mini-eus2-01"
    assert s.otel_prometheus_port == 9464


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]

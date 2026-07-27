"""Unit tests for hello-pipeline env-var loading and required-field enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.pipeline.settings import Settings

REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
    "LANGFUSE_PUBLIC_KEY": "pk-x",
    "LANGFUSE_SECRET_KEY": "sk-x",
}


def test_settings_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    assert s.registered_model_name == "phi-4-mini-meshops"
    assert s.mlflow_tracking_uri.endswith(":5000")
    assert s.otel_prometheus_port == 9464
    assert s.run_interval_seconds == 0


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]

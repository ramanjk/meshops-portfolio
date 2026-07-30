"""Unit tests for hello-security env-var loading and required-field enforcement."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.security.settings import Settings

REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": "https://x.openai.azure.com/",
    "LANGFUSE_PUBLIC_KEY": "pk-x",
    "LANGFUSE_SECRET_KEY": "sk-x",
    "GITHUB_REPO": "owner/repo",
    "GITHUB_TOKEN": "ghp-x",
}


def test_settings_load_with_required(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    assert s.langfuse_host.endswith(":3000")
    assert s.proposal_branch_prefix == "hitl/"
    assert s.otel_prometheus_port == 9464
    assert s.run_interval_seconds == 0
    # Write is off by default -> read-only steward.
    assert s.write_enabled is False
    # Security's default approval channel is synchronous chat, not github_pr.
    assert s.write_approval_channel == "chat"


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in REQUIRED:
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]


def test_allowed_label_set_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("QUARANTINE_ALLOWED_LABELS", "quarantined, security-hold ,, needs-review")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_label_set() == {"quarantined", "security-hold", "needs-review"}
    # First configured label is the default.
    assert s.default_label() == "quarantined"


def test_default_label_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("QUARANTINE_ALLOWED_LABELS", "")
    s = Settings()  # type: ignore[call-arg]
    assert s.allowed_label_set() == set()
    assert s.default_label() == "quarantined"

"""Unit tests for prompt loading.

Guards two things:
  1. The repo persona prompts load and carry the strengthened identity anchoring.
  2. An in-cluster ConfigMap file that exists but is empty must never silently
     shadow the real prompt (the root cause of the "generic AI assistant" bug).
"""
from __future__ import annotations

from pathlib import Path

import stewards.inference.agent as agent


def test_read_prompt_returns_repo_prompt_content() -> None:
    text = agent._read_prompt("inference-steward.chat.md")
    assert "Inference Steward" in text
    # Identity anchoring must be present so the persona holds on a small model.
    assert "non-negotiable" in text.lower()


def test_empty_in_cluster_prompt_falls_back(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "inference-steward.chat.md"
    empty.write_text("", encoding="utf-8")

    orig_path = agent.Path

    def fake_path(arg):
        if str(arg) == "/etc/prompts":
            return tmp_path
        return orig_path(arg)

    monkeypatch.setattr(agent, "Path", fake_path)

    result = agent._read_prompt("inference-steward.chat.md")
    assert result.strip(), "empty in-cluster file must fall back to the repo prompt"
    assert "Inference Steward" in result

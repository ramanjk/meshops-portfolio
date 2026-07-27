"""Unit tests for hello-pipeline prompt loading and empty-file fallback."""
from __future__ import annotations

from pathlib import Path

import stewards.pipeline.agent as agent


def test_read_prompt_returns_repo_prompt_content() -> None:
    text = agent._read_prompt("pipeline-steward.chat.md")
    assert "Pipeline Steward" in text
    assert "non-negotiable" in text.lower()


def test_empty_in_cluster_prompt_falls_back(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "pipeline-steward.chat.md"
    empty.write_text("", encoding="utf-8")

    orig_path = agent.Path

    def fake_path(arg):
        if str(arg) == "/etc/prompts":
            return tmp_path
        return orig_path(arg)

    monkeypatch.setattr(agent, "Path", fake_path)

    result = agent._read_prompt("pipeline-steward.chat.md")
    assert result.strip(), "empty in-cluster file must fall back to the repo prompt"
    assert "Pipeline Steward" in result

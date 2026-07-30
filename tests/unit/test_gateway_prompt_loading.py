"""Unit tests for hello-gateway prompt loading and empty-file fallback."""
from __future__ import annotations

from pathlib import Path

import stewards.gateway.agent as agent


def test_read_prompt_returns_repo_prompt_content() -> None:
    text = agent._read_prompt("gateway-steward.chat.md")
    assert "Gateway Steward" in text
    assert "non-negotiable" in text.lower()


def test_gated_write_persona_present() -> None:
    text = agent._read_prompt("gateway-steward.gated-write.chat.md")
    assert "propose_budget" in text
    assert "HITL gate" in text


def test_empty_in_cluster_prompt_falls_back(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "gateway-steward.chat.md"
    empty.write_text("", encoding="utf-8")

    orig_path = agent.Path

    def fake_path(arg):
        if str(arg) == "/etc/prompts":
            return tmp_path
        return orig_path(arg)

    monkeypatch.setattr(agent, "Path", fake_path)

    result = agent._read_prompt("gateway-steward.chat.md")
    assert result.strip(), "empty in-cluster file must fall back to the repo prompt"
    assert "Gateway Steward" in result

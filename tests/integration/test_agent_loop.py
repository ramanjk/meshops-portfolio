"""Integration tests with the MCP layer and chat client mocked.

We do NOT call Azure OpenAI in iteration-01 tests — the agent loop is
exercised by patching the chat client's `run` method to return a canned
JSON string. The real LLM call is covered by manual case M-04 / M-08.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stewards.inference.schemas import InferenceObservation


@pytest.mark.asyncio
async def test_fixture_observation_parses() -> None:
    """The canned fixture matches the schema."""
    canned = {
        "workspace_name": "lab-phi-4-mini-eus2-01",
        "replica_count": 1,
        "gpu_util_percent": 6.4,
        "summary": "Workspace healthy at 1 replica with GPU utilisation about 6 percent; below 70 percent threshold.",
        "requires_hitl": False,
    }
    InferenceObservation.model_validate(canned)


@pytest.mark.asyncio
async def test_agent_run_returns_validated_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end loop with both MCP servers + the chat client fully mocked."""

    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://fake.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "gpt-4.1")
    monkeypatch.setenv("LANGFUSE_HOST", "http://localhost:3000")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")
    monkeypatch.setenv(
        "AKS_RESOURCE_ID",
        "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/rg/providers/Microsoft.ContainerService/managedClusters/lab",
    )
    monkeypatch.setenv("WORKSPACE_NAMESPACE", "meshops-workloads")
    monkeypatch.setenv("WORKSPACE_NAME", "lab-phi-4-mini-eus2-01")
    monkeypatch.setenv(
        "AZURE_MONITOR_WORKSPACE_QUERY_URL",
        "https://fake.eastus2.prometheus.monitor.azure.com",
    )

    from stewards.inference import agent as agent_module

    canned_json = json.dumps(
        {
            "workspace_name": "lab-phi-4-mini-eus2-01",
            "replica_count": 1,
            "gpu_util_percent": 6.4,
            "summary": "Workspace healthy at 1 replica with GPU utilisation about 6 percent; below 70 percent threshold.",
            "requires_hitl": False,
        }
    )

    class FakeRunResult:
        def __init__(self, text: str) -> None:
            self.text = text

    fake_agent = AsyncMock()
    fake_agent.run.return_value = FakeRunResult(canned_json)

    # `as_agent` is a *synchronous* factory on the real chat client, so it
    # must be a sync mock returning the (async) agent — not an AsyncMock, which
    # would return a coroutine and break `await agent.run(...)`.
    fake_chat = AsyncMock()
    fake_chat.as_agent = MagicMock(return_value=fake_agent)

    class FakeMCPCtx:
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False

    with patch.object(agent_module, "_build_chat_client", return_value=fake_chat), \
         patch.object(agent_module, "MCPStdioTool", return_value=FakeMCPCtx()):
        observation = await agent_module.run_cycle(agent_module.Settings())  # type: ignore[call-arg]

    assert observation.workspace_name == "lab-phi-4-mini-eus2-01"
    assert observation.requires_hitl is False
    assert observation.replica_count == 1

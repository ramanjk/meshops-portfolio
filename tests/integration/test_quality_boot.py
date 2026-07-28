"""Boot-time integration: the quality agent module imports cleanly."""
from __future__ import annotations

import importlib


def test_module_importable() -> None:
    mod = importlib.import_module("stewards.quality.agent")
    assert hasattr(mod, "run")
    assert hasattr(mod, "amain")
    assert hasattr(mod, "run_cycle")


def test_langfuse_mcp_importable() -> None:
    mod = importlib.import_module("mcp_servers.langfuse_mcp.server")
    assert hasattr(mod, "run")
    assert hasattr(mod, "mcp")

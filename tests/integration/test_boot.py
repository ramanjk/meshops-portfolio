"""Boot-time integration: the agent module imports cleanly and exposes `run`."""
from __future__ import annotations

import importlib


def test_module_importable() -> None:
    mod = importlib.import_module("stewards.inference.agent")
    assert hasattr(mod, "run")
    assert hasattr(mod, "amain")
    assert hasattr(mod, "run_cycle")

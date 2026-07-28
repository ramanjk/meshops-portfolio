# Iteration 1 (Read-Only) — Automated Tests: The Safety Net

*Audience: Ram writing the tests; test coverage. These run on your laptop with `uv run pytest` — no Azure spend, no cluster needed.*

It's the moment before you push. You've changed a line in `schemas.py` and you want to know, in under a second, whether you just broke the one promise this whole iteration makes — that the agent cannot write. You type `uv run pytest -q`, watch six green dots appear, and breathe out. That is what this document builds: a fast, honest safety net that fails loudly the instant the no-write guarantee, the schema contract, or the read-only guardrail slips. It is deliberately narrow — iteration-01 is *substrate-proving*, and a test suite that pretends to validate an eval gate that doesn't exist yet would be a lie. So you build exactly what proves AC-1 through AC-10 in CI-able shape, and not one fake test more.

The infographic below shows where these automated checks sit in the full iteration picture — the substrate they guard:

![Iteration-01 — automated test net over the substrate](images/ram-iteration-ig-image-2.png)

***Figure 1: The automated net sits under the observe→reason→report loop, guarding the schema contract, the read-only guardrail, and the metrics endpoint — the parts a code change can silently break.***

## Why the Net Is Intentionally Narrow

```mermaid
pie title Automated test mix — iteration-01
    "Unit (schema + settings)" : 45
    "Integration (mocked MCP + chat)" : 30
    "Read-only eval / guardrail" : 15
    "Smoke (Prom exporter port)" : 10
```

<details>
<summary>ASCII fallback</summary>

```
Unit (schema + settings)        █████ 45%
Integration (mocked MCP + chat) ███ 30%
Read-only eval / guardrail      ██ 15%
Smoke (Prom exporter port)      █ 10%
```

</details>

***Figure 2: The mix. There is no Ragas/Promptfoo eval suite yet (that lands with the Quality Steward); the "eval/guardrail" slice here is the read-only guardrail check that gates the no-write invariant.***

The full LLMOps eval machinery — Ragas, Promptfoo, golden datasets with quality pass-bars — arrives with the Quality Steward in a later iteration, because that is when there is a writable decision whose *quality* matters. In iteration-01 the only decision the agent makes is "report, don't write," so the eval/guardrail layer here is exactly that: a guardrail regression test that fails CI if a prompt or schema change ever lets a write intent through. That is the right-sized version of "agent-quality tests gate CI" for a read-only slice.

**Checkpoint:** You know why the net is small. Next, the framework and what's mocked.

---

## 1. Framework and What's Real vs. Mocked

Where we are in the story: choosing the framework is choosing what you trust. You use **pytest** with **pytest-asyncio** — current, ubiquitous, and the agent loop is `async`, so `asyncio_mode = "auto"` (already set in `pyproject.toml`) lets you write `async def test_…` without ceremony.

What is **real** in these tests: the Pydantic schema, the `Settings` loader, the Prometheus exporter port, and the agent module's import surface. What is **mocked**: Azure OpenAI (the chat client's `run` returns canned JSON — no tokens spent, no flakiness from a live model) and both MCP servers (replaced with a no-op async context manager — no `aks-mcp` binary, no Azure auth needed). Langfuse and Managed Prometheus export are exercised live only in the manual cases M-12 and M-13, because faking them would prove nothing.

```mermaid
sequenceDiagram
    actor Ram
    participant Pytest as uv run pytest
    participant Unit as tests/unit/
    participant Int as tests/integration/
    participant Mock as Mocked MCP + Chat
    participant Port as Local :9464

    Ram->>Pytest: uv run pytest -q
    Pytest->>Unit: test_schemas.py + test_settings.py
    Unit-->>Pytest: pass
    Pytest->>Int: test_agent_loop.py + test_boot.py
    Int->>Mock: AsyncMock create_agent + run
    Mock-->>Int: canned JSON
    Int-->>Pytest: pass
    Pytest->>Int: test_guardrail.py (injection fixture)
    Int-->>Pytest: pass (requires_hitl stays false)
    Pytest->>Port: start_http_server + GET /metrics
    Port-->>Pytest: 200 + non-empty body
    Pytest-->>Ram: all passed
```

***Figure 3: The test run lifecycle. The chat client and MCP servers are mocked; the schema, settings, guardrail, and metrics port are exercised for real.***

<details>
<summary>ASCII fallback</summary>

```
Ram → pytest → tests/unit/        (schema + settings)
              tests/integration/  (agent loop + boot + guardrail, MCP+chat mocked)
              smoke: Prom exporter on a random port, GET /metrics, assert content
       └ all passed
```

</details>

**Checkpoint:** You know the framework and the mock boundary. Next, the test files themselves.

---

## 2. The Tests

`tests/unit/test_schemas.py` and `tests/integration/test_agent_loop.py` are given in full in `02_implementation_guide.md` §8 — create them from there. The remaining four files are below.

### `tests/unit/test_settings.py` → AC-1

*Purpose: prove env-var loading and required-field enforcement.*

```python
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
```

### `tests/integration/test_boot.py` → AC-1

*Purpose: the agent module imports cleanly and exposes its entry points.*

```python
"""Boot-time integration: the agent module imports cleanly and exposes `run`."""
from __future__ import annotations

import importlib


def test_module_importable() -> None:
    mod = importlib.import_module("stewards.inference.agent")
    assert hasattr(mod, "run")
    assert hasattr(mod, "amain")
    assert hasattr(mod, "run_cycle")
```

### `tests/integration/test_guardrail.py` → AC-5, AC-7

*Purpose: the read-only guardrail regression test — a tiny fixed "eval set" of adversarial and benign LLM outputs, asserting the no-write invariant holds. This is the test that fails CI if a prompt or schema change ever lets a write intent through.*

```python
"""Read-only guardrail regression test.

A small fixed set of model-output fixtures stands in for an eval set: each is a
JSON string an LLM *might* return. The pass-bar is the no-write invariant —
every adversarial fixture must be rejected, every benign fixture accepted.
A prompt or schema change that weakens this fails CI.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from stewards.inference.schemas import InferenceObservation

# Benign outputs — must validate cleanly (requires_hitl absent or false).
BENIGN = [
    '{"workspace_name":"lab-phi-4-mini-eus2-01","replica_count":1,'
    '"gpu_util_percent":6.4,"summary":"Healthy at 1 replica; GPU ~6 percent, below threshold.",'
    '"requires_hitl":false}',
    '{"workspace_name":"lab-phi-4-mini-eus2-01","replica_count":0,'
    '"gpu_util_percent":0.0,"summary":"Workspace warming up; GPU node scaling from zero.",'
    '"requires_hitl":false}',
]

# Adversarial outputs — must be rejected (write intent or smuggled action).
ADVERSARIAL = [
    # A prompt-injection win: model flipped requires_hitl true.
    '{"workspace_name":"lab-phi-4-mini-eus2-01","replica_count":1,'
    '"gpu_util_percent":92.0,"summary":"GPU saturated; proposing scale +2 replicas now.",'
    '"requires_hitl":true}',
]


@pytest.mark.parametrize("raw", BENIGN)
def test_benign_outputs_accepted(raw: str) -> None:
    obs = InferenceObservation.model_validate(json.loads(raw))
    assert obs.requires_hitl is False


@pytest.mark.parametrize("raw", ADVERSARIAL)
def test_adversarial_outputs_rejected(raw: str) -> None:
    with pytest.raises(ValidationError):
        InferenceObservation.model_validate(json.loads(raw))


def test_smuggled_action_field_is_dropped() -> None:
    """Even a valid-looking output cannot carry a proposed_actions field forward."""
    raw = (
        '{"workspace_name":"lab-phi-4-mini-eus2-01","replica_count":1,'
        '"gpu_util_percent":40.0,"summary":"Reporting state; an action was smuggled in.",'
        '"requires_hitl":false,"proposed_actions":["kubectl scale --replicas=3"]}'
    )
    obs = InferenceObservation.model_validate(json.loads(raw))
    assert "proposed_actions" not in obs.model_dump()
```

### `tests/integration/test_prom_exporter.py` → AC-9

*Purpose: smoke-test that the Prometheus exporter binds a port and serves metric text.*

```python
"""Smoke: the Prom exporter binds a port and returns Prometheus text on /metrics."""
from __future__ import annotations

import socket
import urllib.request

from prometheus_client import REGISTRY, Counter, start_http_server


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_metrics_endpoint_serves_text() -> None:
    port = _free_port()
    counter = Counter("meshops_test_counter", "test")
    counter.inc()
    start_http_server(port, registry=REGISTRY)
    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics").read().decode()
    assert "meshops_test_counter" in body
    assert "1.0" in body
```

**Checkpoint:** All six test files exist. Next, run them and read the coverage map.

---

## 3. Running the Suite

From the repo root, after `uv sync --extra dev`:

```bash
uv run pytest -q

# Expected:
# ........                                                                  [100%]
# 8 passed in 0.5s
```

If a future test must be skipped (for example, one that needs live Azure OpenAI), mark it `@pytest.mark.skipif(condition, reason="…")` rather than commenting it out — the reason becomes part of the iteration record. There is **no CI runner config this iteration** (Phase 0 is repo-scaffold-only); the first CI YAML lands when the Quality Steward needs Promptfoo to gate a prompt PR. The suite is written CI-ready so that step is a wiring job, not a rewrite.

**Checkpoint:** Green locally. Next, the map from each test to its acceptance criterion and the manual case it backstops.

---

## 4. Coverage Map: Test → Criterion → Manual Backstop

| Test | File | Acceptance criterion | Backstops manual case |
|---|---|---|---|
| T-unit-schema | `tests/unit/test_schemas.py` | AC-4, AC-5 | M-06, M-07 |
| T-unit-config | `tests/unit/test_settings.py` | AC-1 | M-01 |
| T-int-boot | `tests/integration/test_boot.py` | AC-1 | M-01 |
| T-int-agent-loop | `tests/integration/test_agent_loop.py` | AC-2, AC-3, AC-8 | M-03, M-04, M-08 |
| T-eval-guardrail | `tests/integration/test_guardrail.py` | AC-5, AC-7 | M-09, M-10 |
| T-int-prom-exporter | `tests/integration/test_prom_exporter.py` | AC-9 | M-13 |

The guardrail test (`T-eval-guardrail`) is the one that maps to the *operational* acceptance criteria — it is the CI gate that a prompt or model change cannot quietly degrade the no-write guarantee.

---

## 5. What We Deliberately Do Not Automate Yet

Live Azure OpenAI calls (cost + flakiness — the chat client is mocked; the real call is covered by manual M-04). Real Langfuse / Prometheus export (manual M-12, M-13). Real KAITO Workspace observation (manual M-04, M-05). A full Ragas/Promptfoo eval suite with quality pass-bars (arrives with the Quality Steward, when a writable decision's *quality* first matters). A coverage-threshold gate (not in iteration-01).

---

**Sources**

*Repo files:* `040_iterations/iteration-01-read-only/inference/01_use_case.md` · `040_iterations/iteration-01-read-only/inference/02_implementation_guide.md`

*Web:*
- [agent-framework Python samples — observability](https://github.com/microsoft/agent-framework/tree/main/python)
- [Pydantic v2 model validators](https://docs.pydantic.dev/latest/concepts/validators/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/en/latest/)
- [prometheus_client (Python)](https://prometheus.github.io/client_python/)

</content>

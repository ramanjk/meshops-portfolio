"""The hello-sre SRE Steward — read-only correlation.

Wires Microsoft Agent Framework + Azure OpenAI + THREE read substrates —
aks-mcp (in-cluster read-only kubectl), prom-mcp (Azure Managed Prometheus), and
the in-repo langfuse-mcp shim (LLM traces + eval scores) — plus Langfuse OTel
export. Unlike the other stewards, the SRE steward's job is *correlation*: it
joins infra metrics, cluster state, and LLM behaviour into a single incident
timeline + root-cause hypothesis + advice-only remediation.

It proposes nothing in this iteration — the §6 "gated Deployment scale -> HITL"
tail is Iteration 2 (see serve.py + write.py), reachable only when
WRITE_ENABLED=true.

Shape recommended by:
  https://learn.microsoft.com/en-us/agent-framework/agents/observability
  https://langfuse.com/integrations/frameworks/microsoft-agent-framework
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from agent_framework import MCPStdioTool
from agent_framework.observability import configure_otel_providers, get_tracer
from agent_framework.openai import OpenAIChatClient
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from langfuse import get_client
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from prometheus_client import start_http_server
from pydantic import ValidationError

from .schemas import IncidentObservation
from .settings import Settings

LOG = logging.getLogger("meshops.hello-sre")
PROMPT_PATH_DEFAULT = Path("/etc/prompts/sre-steward.system.md")
PROMPT_PATH_LOCAL = Path(__file__).parent.parent.parent.parent / "prompts" / "sre-steward.system.md"


def _read_system_prompt() -> str:
    """Read the system prompt from /etc/prompts in-cluster or the repo path locally.

    An in-cluster file that exists but is empty (e.g. a ConfigMap key that
    rendered blank) is ignored so it can never silently shadow the real prompt.
    """
    if PROMPT_PATH_DEFAULT.exists():
        text = PROMPT_PATH_DEFAULT.read_text(encoding="utf-8")
        if text.strip():
            return text
    return PROMPT_PATH_LOCAL.read_text(encoding="utf-8")


def _read_prompt(filename: str) -> str:
    """Read a prompt file from /etc/prompts in-cluster or ./prompts locally.

    An in-cluster file that exists but is empty is treated as absent and falls
    back to the image-baked prompt, so a blank ConfigMap key cannot wipe the
    persona.
    """
    in_cluster = Path("/etc/prompts") / filename
    if in_cluster.exists():
        text = in_cluster.read_text(encoding="utf-8")
        if text.strip():
            return text
    local = PROMPT_PATH_LOCAL.parent / filename
    return local.read_text(encoding="utf-8")


def build_mcp_tools(settings: Settings) -> tuple[MCPStdioTool, MCPStdioTool, MCPStdioTool]:
    """Construct the three read-only MCP stdio tools (aks-mcp, prom-mcp, langfuse-mcp).

    The MCP stdio client launches each server with a *minimal* default
    environment, which strips the AZURE_* workload-identity vars (needed by
    prom-mcp / langfuse credentials) and the KUBERNETES_* vars (needed by
    aks-mcp's in-cluster kubectl). Forward the pod's full environment so all
    three children authenticate the same way this process does.
    """
    child_env = dict(os.environ)
    aks_tool = MCPStdioTool(
        name="aks-mcp",
        command=settings.aks_mcp_binary,
        args=[
            "--transport",
            "stdio",
            "--access-level",
            settings.aks_mcp_access_level,
            "--enabled-components",
            settings.aks_mcp_enabled_components,
        ],
        env=child_env,
    )
    prom_tool = MCPStdioTool(
        name="prom-mcp",
        command="python",
        args=["-m", "mcp_servers.prom_mcp"],
        env={
            **child_env,
            "AZURE_MONITOR_WORKSPACE_QUERY_URL": settings.azure_monitor_workspace_query_url,
        },
    )
    langfuse_tool = MCPStdioTool(
        name="langfuse-mcp",
        command="python",
        args=["-m", "mcp_servers.langfuse_mcp"],
        env={
            **child_env,
            "LANGFUSE_HOST": settings.langfuse_host,
            "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key,
        },
    )
    return aks_tool, prom_tool, langfuse_tool


def _start_prom_exporter(port: int) -> None:
    """Boot a tiny HTTP server on `port` that exposes Prometheus metrics.

    Azure Managed Prometheus' PodMonitor will scrape this endpoint.
    """
    start_http_server(port)
    LOG.info("Prometheus exporter listening on :%s/metrics", port)


def _build_chat_client(settings: Settings) -> OpenAIChatClient:
    """Build the Azure OpenAI chat client.

    In-cluster: DefaultAzureCredential resolves to Workload Identity.
    Local: AzureCliCredential (after `az login`).
    """
    in_cluster = bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
    credential = DefaultAzureCredential() if in_cluster else AzureCliCredential()
    return OpenAIChatClient(
        credential=credential,
        azure_endpoint=settings.azure_openai_endpoint,
        model=settings.azure_openai_chat_deployment_name,
    )


async def run_cycle(settings: Settings) -> IncidentObservation:
    """Run exactly one observe -> correlate -> report cycle.

    Returns the validated ``IncidentObservation``. Raises on any failure.
    """
    aks_tool, prom_tool, langfuse_tool = build_mcp_tools(settings)

    chat = _build_chat_client(settings)
    system_prompt = _read_system_prompt()

    async with aks_tool, prom_tool, langfuse_tool:
        agent = chat.as_agent(
            name="hello-sre",
            id="hello-sre",
            instructions=system_prompt,
            tools=[aks_tool, prom_tool, langfuse_tool],
        )

        user_turn = (
            "Correlate platform health across metrics, cluster state, and LLM "
            "traces, and report an incident picture.\n"
            f"AKS resource id: {settings.aks_resource_id}\n"
            f"Langfuse host: {settings.langfuse_host}\n"
            f"Sample at most {settings.trace_sample_limit} recent traces.\n\n"
            "Steps:\n"
            "1. Use prom-mcp `query_promql` for platform signals (e.g. 'up', pod "
            "restarts, GPU utilisation like 'DCGM_FI_DEV_GPU_UTIL').\n"
            "2. Use aks-mcp to read workloads, recent events, and node state.\n"
            "3. Use langfuse-mcp `list_traces`/`list_scores` for recent LLM behaviour.\n"
            "4. Correlate the three into ONE picture, then respond ONLY with a JSON "
            "object matching this schema:\n"
            '   { "services_observed": int, "alerts_firing": int,'
            ' "gpu_util_percent": float|null, "error_rate": float|null,'
            ' "traces_observed": int, "incident_suspected": bool,'
            ' "severity": "none"|"low"|"medium"|"high",'
            ' "suspected_root_cause": str, "proposed_remediation": str,'
            ' "summary": str, "requires_hitl": false }\n'
            "proposed_remediation is ADVICE ONLY — do NOT perform or propose any "
            "write. requires_hitl must be false."
        )

        tracer = get_tracer()
        with tracer.start_as_current_span(
            "sre.steward.cycle", kind=SpanKind.CLIENT
        ) as span:
            trace_id_hex = format_trace_id(span.get_span_context().trace_id)
            LOG.info("trace_id=%s", trace_id_hex)

            result = await agent.run(user_turn)

            raw_text = result.text.strip() if hasattr(result, "text") else str(result)
            try:
                payload = json.loads(_extract_json(raw_text))
                observation = IncidentObservation.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                LOG.exception("schema validation failed; failing closed")
                span.record_exception(exc)
                raise

            span.set_attribute("meshops.sre.services_observed", observation.services_observed)
            span.set_attribute("meshops.sre.alerts_firing", observation.alerts_firing)
            span.set_attribute("meshops.sre.incident_suspected", observation.incident_suspected)
            span.set_attribute("meshops.sre.severity", observation.severity)
            return observation


def _extract_json(raw: str) -> str:
    """Defensive JSON extraction from an LLM response, tolerating code-fences."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    return s.strip()


def _enable_langfuse_and_otel(settings: Settings) -> None:
    """Authenticate to Langfuse and turn on MAF OpenTelemetry instrumentation."""
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    os.environ.setdefault("ENABLE_INSTRUMENTATION", "true")
    os.environ.setdefault("ENABLE_SENSITIVE_DATA", "false")

    langfuse = get_client()
    if not langfuse.auth_check():
        raise RuntimeError("Langfuse authentication failed — check LANGFUSE_* secrets.")
    configure_otel_providers(enable_sensitive_data=False)

    reader = PrometheusMetricReader()
    MeterProvider(metric_readers=[reader])


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()  # type: ignore[call-arg]
    _start_prom_exporter(settings.otel_prometheus_port)
    _enable_langfuse_and_otel(settings)

    interval = settings.run_interval_seconds
    if interval <= 0:
        observation = await run_cycle(settings)
        LOG.info("[hello-sre] %s", observation.summary)
        print(observation.model_dump_json())
        return

    LOG.info("[hello-sre] loop mode enabled; running every %ss", interval)
    while True:
        try:
            observation = await run_cycle(settings)
            LOG.info("[hello-sre] %s", observation.summary)
            print(observation.model_dump_json())
        except Exception:
            LOG.exception("[hello-sre] cycle failed; retrying after %ss", interval)
        await asyncio.sleep(interval)


def run() -> None:
    """Entry point for the `hello-sre` console script.

    Three run modes, selected by env/settings:
      * chat_enabled             -> serve the interactive chat API (long-lived).
      * run_interval_seconds > 0 -> loop mode (long-lived, periodic cycles).
      * otherwise                -> one-shot: run a single cycle and exit.
    """
    settings = Settings()  # type: ignore[call-arg]
    if settings.chat_enabled:
        from .serve import serve

        serve(settings)
        return
    asyncio.run(amain())


if __name__ == "__main__":
    run()

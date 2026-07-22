"""The hello-inference Inference Steward — read-only.

Wires Microsoft Agent Framework + Azure OpenAI + two MCP servers
(AKS-MCP read-only + the in-repo Prom-MCP shim) + Langfuse OTel export.

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

from agent_framework import Agent, MCPStdioTool
from agent_framework.openai import OpenAIChatClient
from agent_framework.observability import configure_otel_providers, get_tracer
from azure.identity.aio import AzureCliCredential, DefaultAzureCredential
from langfuse import get_client
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from prometheus_client import start_http_server
from pydantic import ValidationError

from .schemas import InferenceObservation
from .settings import Settings

LOG = logging.getLogger("meshops.hello-inference")
PROMPT_PATH_DEFAULT = Path("/etc/prompts/inference-steward.system.md")
PROMPT_PATH_LOCAL = Path(__file__).parent.parent.parent.parent / "prompts" / "inference-steward.system.md"


def _read_system_prompt() -> str:
    """Read the system prompt from /etc/prompts in-cluster or the repo path locally."""
    if PROMPT_PATH_DEFAULT.exists():
        return PROMPT_PATH_DEFAULT.read_text(encoding="utf-8")
    return PROMPT_PATH_LOCAL.read_text(encoding="utf-8")


def _start_prom_exporter(port: int) -> None:
    """Boot a tiny HTTP server on `port` that exposes Prometheus metrics.

    Azure Managed Prometheus' PodMonitor will scrape this endpoint.
    """
    start_http_server(port)
    LOG.info("Prometheus exporter listening on :%s/metrics", port)


def _build_chat_client(settings: Settings) -> OpenAIChatClient:
    """Build the Azure OpenAI chat client.

    Uses the current agent-framework ``OpenAIChatClient`` with an explicit
    Azure signal (``credential`` + ``azure_endpoint``), which replaces the
    now-deprecated ``AzureOpenAIChatClient``. The deployment name is passed as
    ``model``.

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


async def run_cycle(settings: Settings) -> InferenceObservation:
    """Run exactly one observe -> reason -> report cycle.

    Returns the validated ``InferenceObservation``. Raises on any failure.
    """
    # 1. MCP tool servers — both stdio, both read-only.
    aks_tool = MCPStdioTool(
        name="aks-mcp",
        command=settings.aks_mcp_binary,
        args=["--transport", "stdio", "--access-level", settings.aks_mcp_access_level],
    )
    prom_tool = MCPStdioTool(
        name="prom-mcp",
        command="python",
        args=["-m", "mcp_servers.prom_mcp"],
        env={
            "AZURE_MONITOR_WORKSPACE_QUERY_URL": settings.azure_monitor_workspace_query_url,
        },
    )

    chat = _build_chat_client(settings)
    system_prompt = _read_system_prompt()

    async with aks_tool, prom_tool:
        agent = chat.as_agent(
            name="hello-inference",
            id="hello-inference",
            instructions=system_prompt,
            tools=[aks_tool, prom_tool],
        )

        # Build the human turn — give the LLM exactly what it needs to call tools.
        user_turn = (
            "Observe the KAITO Workspace and report its state.\n"
            f"Subscription resource id: {settings.aks_resource_id}\n"
            f"Workspace namespace: {settings.workspace_namespace}\n"
            f"Workspace name: {settings.workspace_name}\n\n"
            "Steps:\n"
            "1. Use the aks-mcp tool to read the Workspace CR and GPU node metrics.\n"
            "2. Use the prom-mcp tool to query 'kaito_workspace_replicas' for that namespace.\n"
            "3. Respond ONLY with a JSON object matching this schema:\n"
            '   { "workspace_name": str, "replica_count": int, "gpu_util_percent": float,'
            '     "summary": str, "requires_hitl": false }\n'
            "Do NOT propose any action. requires_hitl must be false."
        )

        tracer = get_tracer()
        with tracer.start_as_current_span(
            "inference.steward.cycle", kind=SpanKind.CLIENT
        ) as span:
            trace_id_hex = format_trace_id(span.get_span_context().trace_id)
            LOG.info("trace_id=%s", trace_id_hex)

            result = await agent.run(user_turn)

            raw_text = result.text.strip() if hasattr(result, "text") else str(result)
            try:
                payload = json.loads(_extract_json(raw_text))
                observation = InferenceObservation.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                LOG.exception("schema validation failed; failing closed")
                span.record_exception(exc)
                raise

            span.set_attribute("meshops.workspace.name", observation.workspace_name)
            span.set_attribute("meshops.replica.count", observation.replica_count)
            span.set_attribute("meshops.gpu.util_percent", observation.gpu_util_percent)
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
    """Authenticate to Langfuse and turn on MAF OpenTelemetry instrumentation.

    Per Microsoft's Learn page on Agent Framework Observability,
    `configure_otel_providers()` is the one-call entry point. Langfuse's
    integration page recommends calling it after Langfuse `get_client()`.
    """
    # Langfuse picks up keys from env; we route them in via settings -> os.environ
    # so configuration stays centralized in Settings.
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)
    os.environ.setdefault("ENABLE_INSTRUMENTATION", "true")
    # We deliberately do NOT enable sensitive data in iteration-01.
    os.environ.setdefault("ENABLE_SENSITIVE_DATA", "false")

    langfuse = get_client()
    if not langfuse.auth_check():
        raise RuntimeError("Langfuse authentication failed — check LANGFUSE_* secrets.")
    configure_otel_providers(enable_sensitive_data=False)

    # Add the Prometheus reader to the meter provider so MAF's gen_ai.* metrics
    # show up on :9464.
    reader = PrometheusMetricReader()
    MeterProvider(metric_readers=[reader])


async def amain() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()  # type: ignore[call-arg]
    _start_prom_exporter(settings.otel_prometheus_port)
    _enable_langfuse_and_otel(settings)

    observation = await run_cycle(settings)
    LOG.info("[hello-inference] %s", observation.summary)
    # Structured log line — one JSON object on a line — for downstream ingestion.
    print(observation.model_dump_json())


def run() -> None:
    """Entry point for the `hello-inference` console script."""
    asyncio.run(amain())


if __name__ == "__main__":
    run()

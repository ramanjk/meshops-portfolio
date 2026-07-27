"""The hello-pipeline Pipeline Steward — read-only.

Wires Microsoft Agent Framework + Azure OpenAI + the in-repo MLflow-MCP shim +
Langfuse OTel export. Mirrors stewards/inference/agent.py, but observes an
MLflow model registry instead of a KAITO Workspace, and proposes nothing — the
UC-03 propose -> HITL -> promote tail is deferred to a later iteration.

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

from .schemas import PipelineObservation
from .settings import Settings

LOG = logging.getLogger("meshops.hello-pipeline")
PROMPT_PATH_DEFAULT = Path("/etc/prompts/pipeline-steward.system.md")
PROMPT_PATH_LOCAL = Path(__file__).parent.parent.parent.parent / "prompts" / "pipeline-steward.system.md"


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


def build_mcp_tools(settings: Settings) -> tuple[MCPStdioTool]:
    """Construct the read-only MCP stdio tool(s). The Pipeline steward needs only
    the in-repo mlflow-mcp shim, which reads the MLflow registry over HTTP.

    The MCP stdio client launches the server with a *minimal* default
    environment; forward the pod's full environment so the child authenticates
    and resolves the tracking URI the same way this process does.
    """
    child_env = dict(os.environ)
    mlflow_tool = MCPStdioTool(
        name="mlflow-mcp",
        command="python",
        args=["-m", "mcp_servers.mlflow_mcp"],
        env={
            **child_env,
            "MLFLOW_TRACKING_URI": settings.mlflow_tracking_uri,
        },
    )
    return (mlflow_tool,)


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


async def run_cycle(settings: Settings) -> PipelineObservation:
    """Run exactly one observe -> reason -> report cycle.

    Returns the validated ``PipelineObservation``. Raises on any failure.
    """
    (mlflow_tool,) = build_mcp_tools(settings)

    chat = _build_chat_client(settings)
    system_prompt = _read_system_prompt()

    async with mlflow_tool:
        agent = chat.as_agent(
            name="hello-pipeline",
            id="hello-pipeline",
            instructions=system_prompt,
            tools=[mlflow_tool],
        )

        user_turn = (
            "Observe the MLflow registered model and report its registry state.\n"
            f"MLflow tracking URI: {settings.mlflow_tracking_uri}\n"
            f"Registered model name: {settings.registered_model_name}\n\n"
            "Steps:\n"
            "1. Use the mlflow-mcp tool `get_registered_model` (and "
            "`list_model_versions`) to read the model's versions and their "
            "current_stage (None/Staging/Production/Archived).\n"
            "2. Respond ONLY with a JSON object matching this schema:\n"
            '   { "registered_model_name": str, "total_versions": int,'
            ' "staging_versions": int, "production_versions": int,'
            ' "latest_version": int, "summary": str, "requires_hitl": false }\n'
            "Do NOT propose or perform any promotion. requires_hitl must be false."
        )

        tracer = get_tracer()
        with tracer.start_as_current_span(
            "pipeline.steward.cycle", kind=SpanKind.CLIENT
        ) as span:
            trace_id_hex = format_trace_id(span.get_span_context().trace_id)
            LOG.info("trace_id=%s", trace_id_hex)

            result = await agent.run(user_turn)

            raw_text = result.text.strip() if hasattr(result, "text") else str(result)
            try:
                payload = json.loads(_extract_json(raw_text))
                observation = PipelineObservation.model_validate(payload)
            except (json.JSONDecodeError, ValidationError) as exc:
                LOG.exception("schema validation failed; failing closed")
                span.record_exception(exc)
                raise

            span.set_attribute("meshops.model.name", observation.registered_model_name)
            span.set_attribute("meshops.model.total_versions", observation.total_versions)
            span.set_attribute("meshops.model.staging_versions", observation.staging_versions)
            span.set_attribute("meshops.model.production_versions", observation.production_versions)
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
    # We deliberately do NOT enable sensitive data in iteration-02.
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
        LOG.info("[hello-pipeline] %s", observation.summary)
        print(observation.model_dump_json())
        return

    LOG.info("[hello-pipeline] loop mode enabled; running every %ss", interval)
    while True:
        try:
            observation = await run_cycle(settings)
            LOG.info("[hello-pipeline] %s", observation.summary)
            print(observation.model_dump_json())
        except Exception:  # noqa: BLE001 — resilience: never crash the loop
            LOG.exception("[hello-pipeline] cycle failed; retrying after %ss", interval)
        await asyncio.sleep(interval)


def run() -> None:
    """Entry point for the `hello-pipeline` console script.

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

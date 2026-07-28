"""Environment-loaded settings for the hello-inference steward.

We use pydantic-settings so type errors and missing env vars surface at boot,
not deep inside the agent loop.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration needed to run one hello-inference cycle."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure OpenAI / Foundry
    azure_openai_endpoint: str = Field(
        ..., description="Azure OpenAI endpoint, e.g. https://meshops-aoai.openai.azure.com/"
    )
    azure_openai_chat_deployment_name: str = Field(
        "gpt-4.1", description="Azure OpenAI chat-completion deployment name."
    )

    # Langfuse
    langfuse_host: str = Field(
        "http://langfuse-web.langfuse.svc.cluster.local:3000",
        description="Langfuse base URL — in-cluster service by default.",
    )
    # The two below come from /mnt/secrets/* in-cluster, or .env locally.
    langfuse_public_key: str = Field(..., description="Langfuse public key.")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key.")

    # AKS resource identifiers (Workspace target)
    aks_resource_id: str = Field(
        ...,
        description="Full AKS resource ID, e.g. /subscriptions/.../managedClusters/meshops-lab.",
    )
    workspace_namespace: str = Field("meshops-workloads")
    workspace_name: str = Field("lab-phi-4-mini-eus2-01")

    # MCP server commands
    aks_mcp_binary: str = Field("aks-mcp", description="Path to the aks-mcp binary.")
    aks_mcp_access_level: str = Field(
        "readonly",
        description="Must remain 'readonly' in the read-only iteration (no-write, first layer).",
    )
    aks_mcp_enabled_components: str = Field(
        "kubectl",
        description=(
            "Comma-separated aks-mcp components to enable. The steward only needs "
            "'kubectl' to read the Workspace CR; enabling all components would also "
            "require the az/helm/cilium/hubble binaries to be present in the image."
        ),
    )

    # Managed Prometheus query endpoint (Azure Monitor Workspace)
    azure_monitor_workspace_query_url: str = Field(
        ...,
        description="Azure Monitor managed Prometheus query endpoint, ends with .prometheus.monitor.azure.com",
    )

    # OTel exporter
    otel_prometheus_port: int = Field(9464, description="Port for the in-process Prom exporter.")

    # Run model. 0 (default) = one-shot: run a single cycle and exit (the
    # Job/CronJob pattern). A positive value turns the process into a long-lived
    # loop that runs a cycle, sleeps this many seconds, and repeats — which keeps
    # a Deployment pod in the Running state instead of completing/restarting.
    run_interval_seconds: int = Field(
        0,
        ge=0,
        description="Seconds between cycles in loop mode. 0 = run once and exit.",
    )

    # Interactive chat server. When enabled, the process serves a long-lived
    # HTTP chat API (and minimal web UI) instead of running observe cycles, so
    # you can talk to the steward's persona and exercise its read-only tools.
    chat_enabled: bool = Field(
        False, description="Serve the interactive chat API instead of running cycles."
    )
    chat_port: int = Field(8080, description="Port for the chat HTTP server.")

    # ---- Iteration 2: gated write (HITL) -------------------------------------
    # Master capability flag for the write scope. OFF by default, which makes
    # the steward byte-for-byte its Iteration-1 read-only self: no propose_write
    # tool is wired and the read-only persona is loaded. Turning it ON only makes
    # the HITL gate *reachable* — it never removes the gate (ADR-0011).
    write_enabled: bool = Field(
        False,
        description="Enable the gated-write path (propose -> HITL approve -> act). Off = read-only.",
    )
    # The single namespace the executor is allowed to mutate. Any proposal
    # targeting another namespace is refused before it is even recorded — the
    # application-level twin of the write-but-bounded RBAC Role.
    write_namespace: str = Field(
        "meshops-workloads",
        description="Only namespace the executor may mutate. Backstopped by a namespaced RBAC Role.",
    )
    # Pending proposals expire after this many seconds (single-use, TTL-bounded),
    # so an unapproved proposal cannot linger and be approved much later.
    write_proposal_ttl_seconds: int = Field(
        900,
        ge=30,
        description="Seconds a pending write proposal stays approvable before it expires.",
    )
    # kubectl binary the deterministic executor shells out to for dry-run preview
    # and apply. This is the same actuation aks-mcp performs; it runs under the
    # steward's bounded ServiceAccount token, so RBAC is the hard backstop.
    kubectl_binary: str = Field(
        "kubectl",
        description="Path to kubectl used by the deterministic write executor.",
    )

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
        description="Must remain 'readonly' for iteration-01 (no-write, first layer).",
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

"""Environment-loaded settings for the hello-pipeline steward.

We use pydantic-settings so type errors and missing env vars surface at boot,
not deep inside the agent loop. Mirrors stewards/inference/settings.py, but the
Pipeline steward's substrate is an MLflow model registry (read over HTTP via the
in-repo mlflow-mcp shim) rather than the AKS/Prometheus surface.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration needed to run one hello-pipeline cycle."""

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
    langfuse_public_key: str = Field(..., description="Langfuse public key.")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key.")

    # MLflow model registry (the Pipeline steward's substrate)
    mlflow_tracking_uri: str = Field(
        "http://mlflow.mlflow.svc.cluster.local:5000",
        description="MLflow tracking/registry server base URL — in-cluster service by default.",
    )
    registered_model_name: str = Field(
        "phi-4-mini-meshops",
        description="The registered model the steward observes for promotion-readiness.",
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

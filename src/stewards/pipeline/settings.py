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

    # ---- Iteration 2: gated write (HITL) -------------------------------------
    # Master capability flag for the write scope. OFF by default, which makes the
    # steward byte-for-byte its Iteration-1 read-only self: no propose_promotion
    # tool is wired and the read-only persona is loaded. Turning it ON only makes
    # the HITL gate *reachable* — it never removes the gate (ADR-0011). The one
    # mutation this steward can propose is an MLflow model-version stage
    # transition, bounded to registered_model_name.
    write_enabled: bool = Field(
        False,
        description="Enable the gated-write path (propose -> HITL approve -> act). Off = read-only.",
    )
    # Pending proposals expire after this many seconds (single-use, TTL-bounded).
    write_proposal_ttl_seconds: int = Field(
        900,
        ge=30,
        description="Seconds a pending promotion proposal stays approvable before it expires.",
    )
    # Which HITL approval channel resolves proposals (ADR-0011: pluggable
    # channels on one shared gate + executor + audit).
    #   "chat"       -> interactive Approve/Reject in the chat UI (synchronous).
    #   "github_pr"  -> the steward opens a PR per proposal; MERGE = approve,
    #                   CLOSE = reject. The same in-process executor still applies
    #                   the transition under the same bounded MLflow credentials.
    write_approval_channel: str = Field(
        "chat",
        description="HITL approval channel: 'chat' or 'github_pr'.",
    )
    # --- github_pr channel settings (ignored unless channel == github_pr) ---
    github_repo: str = Field(
        "",
        description="owner/repo the steward opens proposal PRs against (uses the gh CLI).",
    )
    github_base_branch: str = Field(
        "main", description="Base branch proposal PRs target."
    )
    github_proposals_dir: str = Field(
        "hitl-proposals",
        description="Repo directory the proposal file is written to on the PR branch.",
    )
    github_poll_seconds: int = Field(
        20, ge=5, description="How often the reconcile loop polls open proposal PRs."
    )

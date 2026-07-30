"""Environment-loaded settings for the hello-gateway steward.

We use pydantic-settings so type errors and missing env vars surface at boot,
not deep inside the agent loop. The Gateway Steward owns the **LLM routing
plane**: a LiteLLM proxy that fronts the platform's models (here, two logical
routes — ``chat-premium`` and ``chat-economy`` — over Azure OpenAI gpt-4.1), each
with a per-route **budget cap**. In the read-only iteration it reads that plane
via ``litellm-mcp`` (routes + budgets + upstream health) and reports on routing
posture and cost governance.

Iteration 2 adds exactly one gated write — **changing a route's per-route budget
cap** — bounded to an allow-listed set of routes and a budget range, actuated by
deterministic code (patch the LiteLLM config ConfigMap + roll the proxy) under a
namespaced writer Role (never the LLM), through the shared HITL gate (ADR-0011).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration needed to run one hello-gateway cycle."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure OpenAI / Foundry — the steward's OWN reasoning model.
    azure_openai_endpoint: str = Field(
        ..., description="Azure OpenAI endpoint, e.g. https://meshops-aoai.openai.azure.com/"
    )
    azure_openai_chat_deployment_name: str = Field(
        "gpt-4.1", description="Azure OpenAI chat-completion deployment name."
    )

    # Langfuse — OTel export target for the steward's own traces (NOT a read
    # substrate here; the Gateway Steward's substrate is the LiteLLM proxy).
    langfuse_host: str = Field(
        "http://langfuse-web.langfuse.svc.cluster.local:3000",
        description="Langfuse base URL — in-cluster service by default.",
    )
    langfuse_public_key: str = Field(..., description="Langfuse public key.")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key.")

    # LiteLLM proxy — the Gateway Steward's read substrate (via litellm-mcp).
    litellm_base_url: str = Field(
        "http://litellm.meshops-workloads.svc.cluster.local:4000",
        description="Base URL of the LiteLLM proxy the steward reads.",
    )
    litellm_master_key: str = Field(
        ...,
        description="LiteLLM master key used by litellm-mcp for read (admin) endpoints.",
    )

    # OTel exporter
    otel_prometheus_port: int = Field(9464, description="Port for the in-process Prom exporter.")

    # Run model. 0 (default) = one-shot: run a single cycle and exit. A positive
    # value turns the process into a long-lived loop.
    run_interval_seconds: int = Field(
        0,
        ge=0,
        description="Seconds between cycles in loop mode. 0 = run once and exit.",
    )

    # Interactive chat server.
    chat_enabled: bool = Field(
        False, description="Serve the interactive chat API instead of running cycles."
    )
    chat_port: int = Field(8080, description="Port for the chat HTTP server.")

    # ---- Iteration 2: gated write (HITL) -------------------------------------
    # Master capability flag for the write scope. OFF by default, which makes the
    # steward byte-for-byte its Iteration-1 read-only self: no propose_budget
    # tool is wired and the read-only persona is loaded. Turning it ON only makes
    # the HITL gate *reachable* — it never removes the gate (ADR-0011). The one
    # mutation this steward can propose is changing an allow-listed route's
    # per-route budget cap within the configured bounds.
    write_enabled: bool = Field(
        False,
        description="Enable the gated-write path (propose -> HITL approve -> act). Off = read-only.",
    )
    # Pending proposals expire after this many seconds (single-use, TTL-bounded).
    write_proposal_ttl_seconds: int = Field(
        900,
        ge=30,
        description="Seconds a pending budget proposal stays approvable before it expires.",
    )
    # Which HITL approval channel resolves proposals (ADR-0011: pluggable
    # channels on one shared gate + executor + audit).
    #   "chat"       -> interactive Approve/Reject in the chat UI (synchronous).
    #   "github_pr"  -> the steward opens a PR per proposal; MERGE = approve,
    #                   CLOSE = reject.
    write_approval_channel: str = Field(
        "chat",
        description="HITL approval channel: 'chat' or 'github_pr'.",
    )

    # --- budget write bounds (the domain guard, enforced BEFORE the gate) -----
    # The LiteLLM config lives in a ConfigMap; the deterministic applier patches
    # that ConfigMap and rolls the proxy Deployment. All three objects live in
    # the one namespace the writer RBAC Role is bound to (defence-in-depth).
    budget_namespace: str = Field(
        "meshops-workloads",
        description="Namespace holding the LiteLLM ConfigMap + Deployment (the only writable ns).",
    )
    budget_configmap: str = Field(
        "litellm-config",
        description="Name of the ConfigMap holding the LiteLLM config.yaml.",
    )
    budget_config_key: str = Field(
        "config.yaml",
        description="Key within the ConfigMap data holding the LiteLLM config.",
    )
    budget_deployment: str = Field(
        "litellm",
        description="LiteLLM proxy Deployment to roll after a budget change so it reloads config.",
    )
    # Comma-separated allowlist of route (model_name) values the steward may
    # re-budget. Empty = allow any route present in the config.
    budget_allowed_routes: str = Field(
        "",
        description="Comma-separated LiteLLM route names the steward may re-budget. Empty = any.",
    )
    budget_min: float = Field(
        0.0, ge=0.0, description="Lowest per-route budget cap a proposal may request (USD)."
    )
    budget_max: float = Field(
        1000.0, gt=0.0, description="Highest per-route budget cap a proposal may request (USD)."
    )
    kubectl_binary: str = Field("kubectl", description="Path to the kubectl binary for the applier.")

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

    def allowed_route_set(self) -> set[str]:
        """Parse ``budget_allowed_routes`` into a set (empty = unrestricted)."""
        return {r.strip() for r in self.budget_allowed_routes.split(",") if r.strip()}

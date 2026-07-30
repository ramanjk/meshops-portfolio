"""Environment-loaded settings for the hello-sre steward.

We use pydantic-settings so type errors and missing env vars surface at boot,
not deep inside the agent loop. The SRE steward is an **AIOps correlation**
steward: unlike the other stewards, whose value comes from ONE substrate, its
value comes from *joining three read substrates* —

  * Azure Managed Prometheus (platform + GPU + workload metrics, via prom-mcp),
  * the AKS cluster itself (workloads, events, node state, via aks-mcp's
    in-cluster read-only kubectl), and
  * a Langfuse project (LLM traces + eval scores, via langfuse-mcp),

into a single incident timeline + hypothesis + proposed remediation.

Iteration 2 adds exactly one gated write — **scaling a Kubernetes Deployment's
replica count** — bounded to an allow-listed namespace + deployment set and a
replica range, actuated by deterministic code under a namespaced writer Role
(never the LLM), through the shared HITL gate (ADR-0011).
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration needed to run one hello-sre cycle."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure OpenAI / Foundry
    azure_openai_endpoint: str = Field(
        ..., description="Azure OpenAI endpoint, e.g. https://meshops-aoai.openai.azure.com/"
    )
    azure_openai_chat_deployment_name: str = Field(
        "gpt-4.1", description="Azure OpenAI chat-completion deployment name."
    )

    # Langfuse — BOTH the OTel export target AND one of the SRE steward's read
    # substrates (it reads the platform's LLM traces + scores to correlate LLM
    # behaviour against infra metrics).
    langfuse_host: str = Field(
        "http://langfuse-web.langfuse.svc.cluster.local:3000",
        description="Langfuse base URL — in-cluster service by default.",
    )
    langfuse_public_key: str = Field(..., description="Langfuse public key.")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key.")

    # AKS resource identifier — context the aks-mcp read tool needs.
    aks_resource_id: str = Field(
        ...,
        description="Full AKS resource ID, e.g. /subscriptions/.../managedClusters/meshops-lab.",
    )

    # aks-mcp: the SRE steward reads the cluster (workloads, events, nodes) via
    # aks-mcp's in-cluster kubectl. It stays 'readonly' — the gated Deployment
    # scale is actuated by a SEPARATE deterministic kubectl applier (write.py),
    # never through aks-mcp, so the read tool can never mutate.
    aks_mcp_binary: str = Field("aks-mcp", description="Path to the aks-mcp binary.")
    aks_mcp_access_level: str = Field(
        "readonly",
        description="aks-mcp access level. Stays 'readonly'; writes go via the gated kubectl applier.",
    )
    aks_mcp_enabled_components: str = Field(
        "kubectl",
        description="Comma-separated aks-mcp components to enable (only 'kubectl' is needed to read).",
    )

    # Managed Prometheus query endpoint (Azure Monitor Workspace) — prom-mcp.
    azure_monitor_workspace_query_url: str = Field(
        ...,
        description="Azure Monitor managed Prometheus query endpoint (ends with .monitor.azure.com).",
    )

    # How many recent traces to sample from Langfuse per correlation cycle.
    trace_sample_limit: int = Field(
        50,
        ge=1,
        le=100,
        description="Max recent traces to pull from Langfuse per cycle.",
    )

    # OTel exporter
    otel_prometheus_port: int = Field(9464, description="Port for the in-process Prom exporter.")

    # Run model. 0 (default) = one-shot: run a single cycle and exit (the
    # Job/CronJob pattern). A positive value turns the process into a long-lived
    # loop that runs a cycle, sleeps this many seconds, and repeats.
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
    # steward byte-for-byte its Iteration-1 read-only self: no propose_scale tool
    # is wired and the read-only persona is loaded. Turning it ON only makes the
    # HITL gate *reachable* — it never removes the gate (ADR-0011). The one
    # mutation this steward can propose is scaling an allow-listed Deployment's
    # replica count within the configured bounds, in the allowed namespace.
    write_enabled: bool = Field(
        False,
        description="Enable the gated-write path (propose -> HITL approve -> act). Off = read-only.",
    )
    # Pending proposals expire after this many seconds (single-use, TTL-bounded).
    write_proposal_ttl_seconds: int = Field(
        900,
        ge=30,
        description="Seconds a pending scale proposal stays approvable before it expires.",
    )
    # Which HITL approval channel resolves proposals (ADR-0011: pluggable
    # channels on one shared gate + executor + audit).
    #   "chat"       -> interactive Approve/Reject in the chat UI (synchronous).
    #   "github_pr"  -> the steward opens a PR per proposal; MERGE = approve,
    #                   CLOSE = reject. The same in-process executor still runs
    #                   the scale under the same bounded RBAC Role.
    write_approval_channel: str = Field(
        "chat",
        description="HITL approval channel: 'chat' or 'github_pr'.",
    )

    # --- scale write bounds (the domain guard, enforced BEFORE the gate) ------
    # The single namespace the steward's executor may scale into. Must match the
    # namespace its writer RBAC Role is bound to (defence-in-depth).
    scale_namespace: str = Field(
        "meshops-workloads",
        description="The only namespace a scale proposal may target.",
    )
    # Comma-separated allowlist of Deployment names the steward may scale. Empty
    # = allow any Deployment in scale_namespace (still RBAC-bounded to that ns).
    scale_allowed_deployments: str = Field(
        "",
        description="Comma-separated Deployment names the steward may scale. Empty = any in the ns.",
    )
    scale_min_replicas: int = Field(
        0, ge=0, description="Lowest replica count a scale proposal may request."
    )
    scale_max_replicas: int = Field(
        10, ge=1, description="Highest replica count a scale proposal may request."
    )
    kubectl_binary: str = Field("kubectl", description="Path to the kubectl binary for the scaler.")

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

    def allowed_deployment_set(self) -> set[str]:
        """Parse ``scale_allowed_deployments`` into a set (empty = unrestricted)."""
        return {d.strip() for d in self.scale_allowed_deployments.split(",") if d.strip()}

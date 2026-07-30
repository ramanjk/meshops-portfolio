"""Environment-loaded settings for the hello-security steward.

We use pydantic-settings so type errors and missing env vars surface at boot,
not deep inside the agent loop. The Security Steward owns **SecOps for the mesh**:
it classifies the inputs the platform is about to trust — the peer stewards'
Human-in-the-Loop (HITL) proposals (which arrive as GitHub pull requests) and any
other open PR (a runbook / RAG-corpus change) — against a prompt-injection /
confused-deputy / data-poisoning rubric. In the read-only iteration it reads that
proposal queue via ``github-sec-mcp`` (open PRs + their diffs) and reports a
security posture. Classification is **ungated** (it is read-only reasoning).

Iteration 2 adds exactly one gated write — **quarantining a suspicious PR** by
applying an allow-listed label (e.g. ``quarantined``) — actuated by deterministic
code (a single GitHub label write) under a bounded token, never the LLM, through
the shared HITL gate (ADR-0011). Quarantine is gated; classification is not.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration needed to run one hello-security cycle."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Azure OpenAI / Foundry — the steward's OWN reasoning model.
    azure_openai_endpoint: str = Field(
        ..., description="Azure OpenAI endpoint, e.g. https://meshops-aoai.openai.azure.com/"
    )
    azure_openai_chat_deployment_name: str = Field(
        "gpt-4.1", description="Azure OpenAI chat-completion deployment name."
    )

    # Langfuse — OTel export target for the steward's own traces (NOT a read
    # substrate here; the Security Steward's substrate is the GitHub HITL queue).
    langfuse_host: str = Field(
        "http://langfuse-web.langfuse.svc.cluster.local:3000",
        description="Langfuse base URL — in-cluster service by default.",
    )
    langfuse_public_key: str = Field(..., description="Langfuse public key.")
    langfuse_secret_key: str = Field(..., description="Langfuse secret key.")

    # GitHub — the Security Steward's read substrate (via github-sec-mcp) AND the
    # target of its iter-2 quarantine write. Needed in BOTH iterations to read
    # the open proposal queue.
    github_repo: str = Field(
        ..., description="owner/repo whose open PRs (the HITL proposal queue) are classified."
    )
    github_token: str = Field(
        ..., description="GitHub token (repo scope) used to read the queue and, in iter-2, label."
    )
    # Head-branch prefix that marks a peer-steward HITL proposal PR.
    proposal_branch_prefix: str = Field(
        "hitl/", description="Branch prefix identifying a steward HITL proposal PR."
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
    # steward byte-for-byte its Iteration-1 read-only self: no propose_quarantine
    # tool is wired and the read-only persona is loaded. Turning it ON only makes
    # the HITL gate *reachable* — it never removes the gate (ADR-0011). The one
    # mutation this steward can propose is quarantining an open PR by adding an
    # allow-listed label.
    write_enabled: bool = Field(
        False,
        description="Enable the gated-write path (propose -> HITL approve -> act). Off = read-only.",
    )
    # Pending proposals expire after this many seconds (single-use, TTL-bounded).
    write_proposal_ttl_seconds: int = Field(
        900,
        ge=30,
        description="Seconds a pending quarantine proposal stays approvable before it expires.",
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

    # --- quarantine write bounds (the domain guard, enforced BEFORE the gate) --
    # The deterministic applier adds a single GitHub label to the target PR (and
    # an audit comment). Only allow-listed labels may ever be applied.
    quarantine_allowed_labels: str = Field(
        "quarantined,security-hold",
        description="Comma-separated labels the steward may apply. First = default.",
    )

    # --- github_pr channel settings (ignored unless channel == github_pr) ---
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

    def allowed_label_set(self) -> set[str]:
        """Parse ``quarantine_allowed_labels`` into a set."""
        return {lbl.strip() for lbl in self.quarantine_allowed_labels.split(",") if lbl.strip()}

    def default_label(self) -> str:
        """The first configured label — used when the caller does not name one."""
        labels = [lbl.strip() for lbl in self.quarantine_allowed_labels.split(",") if lbl.strip()]
        return labels[0] if labels else "quarantined"

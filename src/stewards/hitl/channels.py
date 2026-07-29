"""Pluggable HITL approval channels, shared by every steward (ADR-0011).

A proposal is created by the :class:`~stewards.hitl.gate.WriteGate`; a *channel*
decides how a human's approve/reject decision reaches the gate. Every channel
feeds the **same** ``WriteGate.approve``/``reject`` — and therefore the same
deterministic executor and the same bounded credentials — so the safety story is
identical no matter how the human says "yes".

This module is domain-agnostic: it renders proposals via ``proposal.human_summary()``
and ``proposal.spec_dict()``, so the very same channels serve the inference
(k8s), pipeline (MLflow) and quality (Langfuse) stewards.

Channels implemented here:

  * :class:`ChatApprovalChannel` — synchronous. The chat UI's ``/approve`` /
    ``/reject`` endpoints call the gate directly; this channel is a no-op.
  * :class:`GitHubPRChannel` — asynchronous. On proposal the steward opens a PR
    whose body is the dry-run preview and whose file is the proposal. **Merging
    the PR = approve; closing it unmerged = reject.** A poll loop reconciles PR
    state into gate decisions. The write is still applied in-process by the
    steward's executor under its bounded credentials — the PR is the *approval
    signal*, not the actuator.

:class:`GitHubClient` is abstracted so the channel is unit-testable with a fake;
the real :class:`GhCliClient` shells out to ``gh api`` (no local checkout needed).
"""
from __future__ import annotations

import base64
import json
import logging
import subprocess
from dataclasses import dataclass
from typing import Protocol

from .gate import Proposal, WriteGate

LOG = logging.getLogger("meshops.hitl")


class ApprovalChannel(Protocol):
    name: str

    def open(self, proposal: Proposal) -> None:
        """Publish ``proposal`` for human decision (sets external_ref if async)."""

    def sync(self, gate: WriteGate) -> list[Proposal]:
        """Reconcile external decisions into gate approve/reject. Returns changed."""


class ChatApprovalChannel:
    """Synchronous chat channel — the /approve,/reject endpoints drive the gate."""

    name = "chat"

    def open(self, proposal: Proposal) -> None:
        return None

    def sync(self, gate: WriteGate) -> list[Proposal]:
        return []


# --------------------------------------------------------------------------- #
# GitHub PR channel
# --------------------------------------------------------------------------- #

@dataclass
class PRRef:
    number: int
    url: str


@dataclass
class PRStatus:
    state: str          # "open" | "closed"
    merged: bool
    decided_by: str | None


class GitHubClient(Protocol):
    def create_pr(
        self, *, branch: str, base: str, title: str, body: str, path: str, content: str
    ) -> PRRef: ...
    def pr_status(self, number: int) -> PRStatus: ...


class GhCliClient:
    """GitHubClient backed by ``gh api`` (REST) — no local git mutation."""

    def __init__(self, repo: str, gh_binary: str = "gh", timeout_seconds: int = 30) -> None:
        self._repo = repo
        self._gh = gh_binary
        self._timeout = timeout_seconds

    def _api(self, path: str, *args: str, method: str | None = None) -> dict:
        argv = [self._gh, "api"]
        if method:
            argv += ["-X", method]
        argv += [f"repos/{self._repo}/{path}", *args]
        proc = subprocess.run(  # noqa: S603 - argv built from validated config
            argv, capture_output=True, text=True, timeout=self._timeout
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "gh api failed").strip())
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def create_pr(self, *, branch: str, base: str, title: str, body: str, path: str, content: str) -> PRRef:
        base_sha = self._api(f"git/ref/heads/{base}")["object"]["sha"]
        self._api("git/refs", "-f", f"ref=refs/heads/{branch}", "-f", f"sha={base_sha}", method="POST")
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        self._api(
            f"contents/{path}",
            "-f", f"message={title}", "-f", f"content={encoded}", "-f", f"branch={branch}",
            method="PUT",
        )
        pr = self._api(
            "pulls",
            "-f", f"title={title}", "-f", f"head={branch}", "-f", f"base={base}", "-f", f"body={body}",
            method="POST",
        )
        return PRRef(number=int(pr["number"]), url=pr["html_url"])

    def pr_status(self, number: int) -> PRStatus:
        pr = self._api(f"pulls/{number}")
        merged = bool(pr.get("merged_at"))
        decided_by = None
        if merged and pr.get("merged_by"):
            decided_by = pr["merged_by"].get("login")
        return PRStatus(state=pr.get("state", "open"), merged=merged, decided_by=decided_by)


class GitHubPRChannel:
    """Asynchronous channel: PR merge = approve, PR close = reject."""

    name = "github_pr"

    def __init__(self, client: GitHubClient, *, base_branch: str, proposals_dir: str) -> None:
        self._client = client
        self._base = base_branch
        self._dir = proposals_dir.strip("/")

    def open(self, proposal: Proposal) -> None:
        branch = f"hitl/{proposal.id}"
        path = f"{self._dir}/{proposal.id}.md"
        title = f"HITL: {proposal.human_summary()}"
        body = self._pr_body(proposal)
        try:
            ref = self._client.create_pr(
                branch=branch, base=self._base, title=title, body=body,
                path=path, content=body,
            )
        except Exception as exc:
            LOG.warning("[write] could not open PR for %s: %s", proposal.id, exc)
            proposal.external_ref = f"(PR creation failed: {exc})"
            return
        proposal.external_id = str(ref.number)
        proposal.external_ref = ref.url
        LOG.info("[write] proposal %s opened as PR #%s", proposal.id, ref.number)

    def sync(self, gate: WriteGate) -> list[Proposal]:
        changed: list[Proposal] = []
        for proposal in gate.pending_all():
            if not proposal.external_id:
                continue
            try:
                status = self._client.pr_status(int(proposal.external_id))
            except Exception as exc:
                LOG.debug("[write] poll failed for %s (PR %s): %s", proposal.id, proposal.external_id, exc)
                continue
            if status.merged:
                gate.approve(proposal.id, status.decided_by or "github-merge")
                changed.append(proposal)
            elif status.state == "closed":
                gate.reject(proposal.id, "github-close")
                changed.append(proposal)
        return changed

    @staticmethod
    def _pr_body(proposal: Proposal) -> str:
        return (
            f"# HITL write proposal `{proposal.id}`\n\n"
            f"**Intent:** {proposal.human_summary()}\n\n"
            f"**Rationale:** {proposal.rationale}\n\n"
            f"> Merging this PR **approves** the write; closing it **rejects** it. "
            f"The steward's deterministic executor applies it in-process under its "
            f"own bounded credentials (ADR-0011) — the PR is the approval signal, "
            f"not the actuator.\n\n"
            f"## Dry-run preview\n\n```\n{proposal.preview}\n```\n\n"
            f"## Proposal\n\n```json\n{json.dumps(proposal.spec_dict(), indent=2)}\n```\n"
        )


def build_channel(settings, gate: WriteGate) -> ApprovalChannel:
    """Construct the approval channel named by settings.write_approval_channel."""
    if settings.write_approval_channel == "github_pr":
        if not settings.github_repo:
            raise ValueError("write_approval_channel='github_pr' requires github_repo (owner/repo).")
        return GitHubPRChannel(
            GhCliClient(settings.github_repo),
            base_branch=settings.github_base_branch,
            proposals_dir=settings.github_proposals_dir,
        )
    return ChatApprovalChannel()

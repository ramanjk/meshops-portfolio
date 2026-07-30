"""Iteration-2 gated write for the Security steward: quarantine a suspicious PR.

The Security Steward reads the HITL proposal queue (open PRs) and classifies each
input against a prompt-injection / confused-deputy / data-poisoning rubric. Its
*one* mutation is **quarantining a PR** — applying an allow-listed label (e.g.
``quarantined``) so the input is held back from being trusted/merged. Per the
agent catalog, *classification is ungated; quarantine is gated*: the label write
still passes the human gate (ADR-0011).

This module supplies the two domain pieces the shared HITL spine
(:mod:`stewards.hitl`) needs:

  * :class:`QuarantineProposal` — the intent (PR number + label to apply).
  * :class:`GitHubLabelApplier` — deterministic preview/apply that reads the PR
    and adds the label via the GitHub REST API under a bounded token, then leaves
    an audit comment.

Three layers cap blast radius (defence-in-depth):
  1. persona — the read-only persona has no propose tool at all;
  2. domain guard — :func:`build_propose_quarantine_tool` rejects any label
     outside the allowlist *before* the gate stores it (recorded via
     :meth:`WriteGate.deny`, never approvable);
  3. token scope — the write is a single GitHub *label* add via a repo-scoped
     token; unlike the other stewards this steward never touches the cluster, so
     an approved-but-wrong request is capped to "add an allow-listed label to a
     PR" — it can neither merge, close, nor push code.

The LLM only ever calls :func:`build_propose_quarantine_tool`, which records a
proposal and returns ``PENDING``. It has no path to actuation (ADR-0011).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from pydantic import Field

from ..hitl import ApplyError, Proposal, ProposalStatus, WriteGate, current_session_id

LOG = logging.getLogger("meshops.hello-security.write")

_API_DEFAULT = "https://api.github.com"


class QuarantineProposal(Proposal):
    """A proposed quarantine (label application) for one open pull request."""

    pr_number: int = Field(..., ge=1, le=1_000_000)
    label: str = Field(..., min_length=1, max_length=100)

    def human_summary(self) -> str:
        return f"quarantine PR #{self.pr_number} by applying label '{self.label}'"

    def spec_dict(self) -> dict:
        return {
            "kind": "PullRequestQuarantine",
            "pr_number": self.pr_number,
            "label": self.label,
        }

    def audit_kind(self) -> str:
        return "pr-quarantine"


def _as_quarantine(proposal: Proposal) -> QuarantineProposal:
    if not isinstance(proposal, QuarantineProposal):
        raise ApplyError(f"expected a QuarantineProposal, got {type(proposal).__name__}")
    return proposal


class GitHubLabelApplier:
    """Deterministic executor: add an allow-listed label to a PR via GitHub REST.

    The quarantine write is a single label application (plus an audit comment) on
    the target pull request, done with the GitHub REST API under a repo-scoped
    token. There is no cluster access at all. All actuation is deterministic code
    (never the LLM).
    """

    def __init__(
        self,
        *,
        repo: str,
        token: str,
        api_base: str = _API_DEFAULT,
        timeout_seconds: int = 20,
    ) -> None:
        self._repo = repo.strip("/")
        self._token = token
        self._api = api_base.rstrip("/")
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {self._token}",
        }

    def _get_pr(self, pr_number: int) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self._api}/repos/{self._repo}/pulls/{pr_number}", headers=self._headers()
            )
        if resp.status_code == 404:
            raise ApplyError(f"PR #{pr_number} not found in {self._repo}")
        if resp.status_code in (401, 403):
            raise ApplyError(f"GitHub denied the request ({resp.status_code})", denied=True)
        if resp.status_code >= 400:
            raise ApplyError(f"GitHub error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def preview(self, proposal: Proposal) -> str:
        """Dry-run: confirm the PR is open and describe the label that would be added.

        Reading the PR first surfaces "PR not found", "already closed", or a
        token-forbidden error *before* approval.
        """
        proposal = _as_quarantine(proposal)
        pr = self._get_pr(proposal.pr_number)
        state = pr.get("state")
        title = (pr.get("title") or "")[:120]
        current = [lbl.get("name") for lbl in pr.get("labels", [])]
        already = " (already present)" if proposal.label in current else ""
        closed_note = "" if state == "open" else f" WARNING: PR is '{state}', not open."
        return (
            f"PR #{proposal.pr_number} '{title}' [{state}]: would add label "
            f"'{proposal.label}'{already}. Current labels: {current or 'none'}."
            f"{closed_note} No change made (dry-run)."
        )

    def apply(self, proposal: Proposal) -> str:
        proposal = _as_quarantine(proposal)
        # Verify the PR exists (and capture state) before mutating.
        pr = self._get_pr(proposal.pr_number)
        with httpx.Client(timeout=self._timeout) as client:
            add = client.post(
                f"{self._api}/repos/{self._repo}/issues/{proposal.pr_number}/labels",
                headers=self._headers(),
                json={"labels": [proposal.label]},
            )
            if add.status_code in (401, 403):
                raise ApplyError(
                    f"GitHub denied the label write ({add.status_code})", denied=True
                )
            if add.status_code >= 400:
                raise ApplyError(f"GitHub label add failed {add.status_code}: {add.text[:200]}")
            # Best-effort audit comment; do not fail the quarantine if it errors.
            try:
                client.post(
                    f"{self._api}/repos/{self._repo}/issues/{proposal.pr_number}/comments",
                    headers=self._headers(),
                    json={
                        "body": (
                            f"🔒 **Quarantined by hello-security** — label "
                            f"`{proposal.label}` applied via the HITL gate.\n\n"
                            f"Rationale: {proposal.rationale}"
                        )
                    },
                )
            except httpx.HTTPError as exc:  # pragma: no cover - network dependent
                LOG.warning("[write] label applied but audit comment failed: %s", exc)
        state = pr.get("state")
        return (
            f"applied label '{proposal.label}' to PR #{proposal.pr_number} "
            f"(state={state}) in {self._repo}"
        )


def build_propose_quarantine_tool(
    gate: WriteGate,
    *,
    allowed_labels: set[str],
    default_label: str,
) -> Callable[..., str]:
    """Build the ``propose_quarantine`` callable bound to ``gate`` for MAF to expose.

    The domain guard (label allowlist) is enforced here, *before* the proposal is
    stored — a violating request is recorded via :meth:`WriteGate.deny` so it can
    never be approved.
    """

    def propose_quarantine(
        pr_number: int,
        rationale: str,
        label: str | None = None,
    ) -> str:
        """Propose quarantining an open PR by applying a label. Does NOT execute.

        Call this only when you have classified a PR as suspicious or malicious
        (prompt injection, confused-deputy, or data poisoning) and a human should
        hold it back. It records the proposal and returns a PENDING ticket. You
        MUST then show the user the proposal id and preview and ask them to
        approve or reject. NEVER claim the PR was quarantined — it has not been,
        and will not be, until the human approves.

        Args:
            pr_number: the open PR number to quarantine (from the read tool).
            rationale: one sentence on why this PR is being quarantined.
            label: the quarantine label to apply; defaults to the configured one.

        Returns:
            A human-readable PENDING string with the proposal id and dry-run preview.
        """
        chosen = (label or default_label).strip()
        try:
            proposal = QuarantineProposal(
                pr_number=pr_number,
                label=chosen,
                rationale=rationale,
                session_id=current_session_id.get(),
            )
        except Exception as exc:  # surface validation errors to the LLM as text
            LOG.warning("[write] propose rejected: %s", exc)
            return f"PROPOSAL REJECTED (not recorded): {exc}"

        # --- domain guard: bound the label to the allowlist -------------------
        if allowed_labels and chosen not in allowed_labels:
            allowed = ", ".join(sorted(allowed_labels))
            reason = f"label '{chosen}' is not in the quarantine allowlist ({allowed})."
            proposal = gate.deny(proposal, reason)
            return f"PROPOSAL DENIED: {reason} No change was or will be made."

        proposal = gate.submit(proposal)
        if proposal.status == ProposalStatus.DENIED:
            return f"PROPOSAL DENIED: {proposal.outcome} No change was or will be made."

        return (
            f"PROPOSAL {proposal.id} recorded and is PENDING human approval — "
            f"nothing has been changed.\n"
            f"Intent: {proposal.human_summary()}\n"
            f"Rationale: {proposal.rationale}\n"
            f"Dry-run preview:\n{proposal.preview}\n\n"
            f"Tell the user exactly what will happen and ask them to Approve or "
            f"Reject proposal {proposal.id}. Do NOT say it is done."
        )

    return propose_quarantine

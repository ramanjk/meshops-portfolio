"""Generic gated-write HITL machinery shared by every steward (ADR-0011).

This is the domain-agnostic distillation of the inference steward's Iteration-2
gate. It carries **no** Kubernetes/MLflow/Langfuse specifics: a steward supplies

  * a :class:`Proposal` subclass describing *its* mutation (a registry promotion,
    a trace annotation, a k8s patch, …), and
  * an :class:`Applier` that deterministically previews/executes that proposal
    against the steward's own substrate under bounded credentials.

The invariant is identical across stewards and channels:

  * The LLM never actuates. Its only write-adjacent tool records a *proposal* and
    returns ``PENDING`` — the tool lives in each steward's ``write`` module.
  * A :class:`WriteGate` holds pending proposals (single-use, TTL-bounded) and is
    the *only* object that can transition one to *executed* — and only via
    :meth:`WriteGate.approve`, i.e. only after a human decision.
  * A deterministic :class:`Applier` performs the mutation; the steward's bounded
    credentials (RBAC Role, scoped MLflow model, scoped Langfuse project) are the
    hard backstop even for an approved-but-wrong request.
  * Every transition is written to an append-only :class:`AuditSink`.

Nothing here can mutate anything without a prior :meth:`WriteGate.approve` call.
The module is free of LLM/agent imports so it can be unit-tested in isolation.
"""
from __future__ import annotations

import enum
import json
import logging
import secrets
import time
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, Field

LOG = logging.getLogger("meshops.hitl")


class ProposalStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    REJECTED = "rejected"
    DENIED = "denied"
    EXPIRED = "expired"


class Proposal(BaseModel):
    """Base class for a single pending (or resolved) mutation.

    A steward subclasses this with the *intent* fields for its own domain and
    overrides :meth:`human_summary` and :meth:`spec_dict`. The gate assigns
    ``id``, ``created_at`` and ``preview`` and drives ``status`` — subclasses
    never set those directly.
    """

    id: str = Field("", description="Single-use token, e.g. 'pw_ab12cd34'. Assigned by the gate.")
    rationale: str = Field(..., min_length=10, max_length=800)

    status: ProposalStatus = ProposalStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    preview: str | None = None
    outcome: str | None = None
    session_id: str | None = None
    approver: str | None = None
    # Set by an async approval channel (e.g. github_pr): the external artifact
    # that carries the human decision. external_ref is a URL for display;
    # external_id is the machine key the channel polls (e.g. PR number).
    external_ref: str | None = None
    external_id: str | None = None

    # -- subclass contract ----------------------------------------------------
    def human_summary(self) -> str:
        """A one-line description of the intended mutation for approval prompts."""
        raise NotImplementedError

    def spec_dict(self) -> dict:
        """The machine-readable intent (rendered into the PR body / audit)."""
        raise NotImplementedError

    def audit_kind(self) -> str:
        """Short label for the audit stream (defaults to the class name)."""
        return type(self).__name__

    # -- shared helpers -------------------------------------------------------
    def is_terminal(self) -> bool:
        return self.status != ProposalStatus.PENDING


class ApplyError(RuntimeError):
    """Raised by an Applier when a preview or apply fails (incl. auth denial)."""

    def __init__(self, message: str, *, denied: bool = False) -> None:
        super().__init__(message)
        self.denied = denied


class Applier(Protocol):
    """Performs the actual mutation. Deterministic; never sees the LLM."""

    def preview(self, proposal: Proposal) -> str:
        """Return a dry-run description of ``proposal`` (makes no change)."""

    def apply(self, proposal: Proposal) -> str:
        """Execute ``proposal`` for real; return a short outcome string."""


class AuditSink(Protocol):
    """Append-only audit. The production sink is immutable Azure Storage."""

    def record(self, event: dict) -> None: ...


class LoggingAuditSink:
    """Default sink: one structured JSON line per event on the audit logger.

    A real deployment swaps this for an immutable Azure Storage writer (ADR-0011
    requires immutability); the :class:`WriteGate` depends only on the protocol.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("meshops.hitl.audit")

    def record(self, event: dict) -> None:
        self._log.info("AUDIT %s", json.dumps(event, sort_keys=True, default=str))


class WriteGate:
    """Holds pending proposals and is the only path from proposal to execution.

    A proposal can only ever leave PENDING through :meth:`approve` (which runs the
    applier) or :meth:`reject` — both of which require an out-of-band human call.
    Approval is single-use and TTL-bounded. Domain guards (e.g. "only this model
    is writable") are enforced by the steward's propose tool *before* it calls
    :meth:`submit`; a rejected-at-guard proposal is recorded via :meth:`deny`.
    """

    def __init__(
        self,
        applier: Applier,
        *,
        ttl_seconds: int,
        audit: AuditSink | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._applier = applier
        self._ttl = ttl_seconds
        self._audit = audit or LoggingAuditSink()
        self._clock = clock
        self._store: dict[str, Proposal] = {}

    # -- proposal creation (called by the steward's non-mutating tool) --------
    def submit(self, proposal: Proposal) -> Proposal:
        """Record a pending proposal and compute its dry-run preview. Never mutates."""
        proposal.id = proposal.id or self._token()
        proposal.created_at = self._clock()
        try:
            proposal.preview = self._applier.preview(proposal)
        except ApplyError as exc:
            # A failed dry-run is useful signal — keep the proposal pending but
            # surface the error so the human can judge (or reject) it.
            proposal.preview = f"(dry-run failed) {exc}"
        self._store[proposal.id] = proposal
        self._audit_event("proposed", proposal)
        return proposal

    def deny(self, proposal: Proposal, reason: str) -> Proposal:
        """Record a proposal refused by a domain guard before it becomes approvable.

        The app-level twin of an authz denial: audited, never stored as pending,
        so it can never be approved.
        """
        proposal.id = proposal.id or self._token()
        proposal.status = ProposalStatus.DENIED
        proposal.outcome = reason
        self._audit_event("denied", proposal)
        return proposal

    # -- human decisions ------------------------------------------------------
    def approve(self, token: str, approver: str) -> Proposal:
        proposal = self._require_pending(token)
        proposal.approver = approver
        try:
            proposal.outcome = self._applier.apply(proposal)
            proposal.status = ProposalStatus.EXECUTED
            self._audit_event("executed", proposal)
        except ApplyError as exc:
            proposal.status = ProposalStatus.DENIED if exc.denied else ProposalStatus.FAILED
            proposal.outcome = str(exc)
            self._audit_event("denied" if exc.denied else "failed", proposal)
        return proposal

    def reject(self, token: str, approver: str) -> Proposal:
        proposal = self._require_pending(token)
        proposal.approver = approver
        proposal.status = ProposalStatus.REJECTED
        proposal.outcome = "rejected by approver; no change made."
        self._audit_event("rejected", proposal)
        return proposal

    # -- lookups --------------------------------------------------------------
    def get(self, token: str) -> Proposal | None:
        proposal = self._store.get(token)
        if proposal and proposal.status == ProposalStatus.PENDING and self._expired(proposal):
            proposal.status = ProposalStatus.EXPIRED
            self._audit_event("expired", proposal)
        return proposal

    def pending_for_session(self, session_id: str) -> list[Proposal]:
        return [
            p for p in self._store.values()
            if p.session_id == session_id and p.status == ProposalStatus.PENDING and not self._expired(p)
        ]

    def pending_all(self) -> list[Proposal]:
        """All still-approvable proposals, regardless of session.

        Used by async approval channels (e.g. github_pr) to reconcile external
        decisions (PR merged/closed) against the gate. Expiry is applied lazily.
        """
        out: list[Proposal] = []
        for p in list(self._store.values()):
            if p.status != ProposalStatus.PENDING:
                continue
            if self._expired(p):
                p.status = ProposalStatus.EXPIRED
                self._audit_event("expired", p)
                continue
            out.append(p)
        return out

    # -- internals ------------------------------------------------------------
    def _require_pending(self, token: str) -> Proposal:
        proposal = self._store.get(token)
        if proposal is None:
            raise KeyError(f"no such proposal '{token}'")
        if self._expired(proposal) and proposal.status == ProposalStatus.PENDING:
            proposal.status = ProposalStatus.EXPIRED
            self._audit_event("expired", proposal)
        if proposal.is_terminal():
            raise ValueError(f"proposal '{token}' is already {proposal.status.value}; single-use.")
        return proposal

    def _expired(self, proposal: Proposal) -> bool:
        return (self._clock() - proposal.created_at) > self._ttl

    def _token(self) -> str:
        return f"pw_{secrets.token_hex(4)}"

    def _audit_event(self, event: str, proposal: Proposal) -> None:
        self._audit.record(
            {
                "event": event,
                "ts": self._clock(),
                "proposal_id": proposal.id,
                "kind": proposal.audit_kind(),
                "target": proposal.human_summary(),
                "status": proposal.status.value,
                "approver": proposal.approver,
                "session_id": proposal.session_id,
                "outcome": proposal.outcome,
            }
        )

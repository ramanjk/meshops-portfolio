"""The Iteration-2 gated-write HITL machinery for the inference steward.

This module is the executable form of ADR-0011 (*no autonomous actuation*).
It is deliberately self-contained and free of any LLM/agent imports so it can
be unit-tested in isolation and reasoned about on its own.

The shape (ADR-0011 §Decision):

  * The LLM never actuates. Its only write-adjacent tool records a *proposal*
    and returns ``PENDING`` — see ``propose_write_tool`` in ``write_tool.py``.
  * A ``WriteGate`` holds pending proposals (single-use, TTL-bounded) and is the
    only object that can transition one to *executed* — and only via
    ``approve()``, i.e. only after a human decision.
  * A deterministic ``Applier`` performs the actual mutation. ``KubectlApplier``
    shells out to ``kubectl`` under the steward's bounded ServiceAccount token —
    the same actuation aks-mcp performs — so the write-but-bounded RBAC Role is
    the hard backstop even for an approved-but-wrong request.
  * Every transition is written to an append-only ``AuditSink``.

Nothing here can mutate the cluster without a prior ``approve()`` call.
"""
from __future__ import annotations

import enum
import json
import logging
import secrets
import subprocess
import time
from collections.abc import Callable
from typing import Protocol, Self

from pydantic import BaseModel, Field, model_validator

LOG = logging.getLogger("meshops.hello-inference.write")

# Bounds for the one numeric parameter we accept, mirroring the read-only
# InferenceObservation.replica_count bounds so a scale can never ask for a wild
# number even before RBAC/quota would reject it.
MIN_REPLICAS = 0
MAX_REPLICAS = 100


class WriteOperation(enum.StrEnum):
    """The mutating verbs the gate understands.

    This is *not* an allowlist of business actions — it is the small set of
    generic Kubernetes mutation shapes any write reduces to. Safety comes from
    the gate + preview + human approval + bounded RBAC, not from this enum.
    """

    CREATE = "create"
    APPLY = "apply"
    PATCH = "patch"
    SCALE = "scale"
    DELETE = "delete"


class ProposalStatus(enum.StrEnum):
    PENDING = "pending"
    EXECUTED = "executed"
    FAILED = "failed"
    REJECTED = "rejected"
    DENIED = "denied"
    EXPIRED = "expired"


class WriteProposal(BaseModel):
    """A single pending (or resolved) mutation the steward wants to make.

    Created by ``WriteGate.propose`` — never by the LLM directly. The LLM only
    supplies the *intent* fields; the gate assigns ``id``, ``created_at``,
    ``preview`` and drives ``status``.
    """

    id: str = Field(..., description="Single-use token, e.g. 'pw_ab12cd34'.")
    operation: WriteOperation
    resource_kind: str = Field(..., min_length=1, description="e.g. 'Pod', 'Deployment', 'Workspace'.")
    namespace: str = Field(..., min_length=1)
    name: str | None = Field(None, description="Resource name; required for patch/scale/delete.")
    manifest: dict | None = Field(None, description="Full object for create/apply.")
    patch: dict | None = Field(None, description="Strategic-merge patch body for patch.")
    replicas: int | None = Field(None, ge=MIN_REPLICAS, le=MAX_REPLICAS, description="Target for scale.")
    rationale: str = Field(..., min_length=10, max_length=800)

    status: ProposalStatus = ProposalStatus.PENDING
    created_at: float = Field(default_factory=time.time)
    preview: str | None = None
    outcome: str | None = None
    session_id: str | None = None
    approver: str | None = None

    @model_validator(mode="after")
    def _shape_matches_operation(self) -> Self:
        op = self.operation
        if op in (WriteOperation.CREATE, WriteOperation.APPLY) and not self.manifest:
            raise ValueError(f"operation '{op.value}' requires a 'manifest'.")
        if op == WriteOperation.PATCH and not self.patch:
            raise ValueError("operation 'patch' requires a 'patch' body.")
        if op == WriteOperation.PATCH and not self.name:
            raise ValueError("operation 'patch' requires a target 'name'.")
        if op == WriteOperation.SCALE and (self.replicas is None or not self.name):
            raise ValueError("operation 'scale' requires 'name' and 'replicas'.")
        if op == WriteOperation.DELETE and not self.name:
            raise ValueError("operation 'delete' requires a target 'name'.")
        return self

    def is_terminal(self) -> bool:
        return self.status != ProposalStatus.PENDING

    def human_summary(self) -> str:
        """A one-line description of the intended mutation for approval prompts."""
        target = f"{self.resource_kind}/{self.name}" if self.name else self.resource_kind
        detail = ""
        if self.operation == WriteOperation.SCALE:
            detail = f" -> replicas={self.replicas}"
        return f"{self.operation.value} {target} in ns/{self.namespace}{detail}"


class ApplyError(RuntimeError):
    """Raised by an Applier when a preview or apply fails (incl. RBAC denial)."""

    def __init__(self, message: str, *, denied: bool = False) -> None:
        super().__init__(message)
        self.denied = denied


class Applier(Protocol):
    """Performs the actual mutation. Deterministic; never sees the LLM."""

    def preview(self, proposal: WriteProposal) -> str:
        """Return the server dry-run result for ``proposal`` (no change made)."""

    def apply(self, proposal: WriteProposal) -> str:
        """Execute ``proposal`` for real; return a short outcome string."""


class AuditSink(Protocol):
    """Append-only audit. The production sink is immutable Azure Storage."""

    def record(self, event: dict) -> None: ...


class LoggingAuditSink:
    """Default sink: one structured JSON line per event on the audit logger.

    A real deployment swaps this for an immutable Azure Storage writer (ADR-0011
    requires immutability); the ``WriteGate`` depends only on the protocol.
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("meshops.hello-inference.audit")

    def record(self, event: dict) -> None:
        self._log.info("AUDIT %s", json.dumps(event, sort_keys=True, default=str))


class KubectlApplier:
    """Applier that shells out to ``kubectl`` under the pod's bounded token.

    This is the same actuation aks-mcp's kubectl component performs; running it
    in-process from *deterministic* code (never the LLM) keeps the "model cannot
    actuate" invariant while still going through the same tool. The write-but-
    bounded RBAC Role is what actually caps blast radius.
    """

    def __init__(self, kubectl_binary: str = "kubectl", timeout_seconds: int = 30) -> None:
        self._kubectl = kubectl_binary
        self._timeout = timeout_seconds

    def preview(self, proposal: WriteProposal) -> str:
        return self._run(proposal, dry_run=True)

    def apply(self, proposal: WriteProposal) -> str:
        return self._run(proposal, dry_run=False)

    def _argv(self, proposal: WriteProposal, dry_run: bool) -> tuple[list[str], str | None]:
        ns = ["-n", proposal.namespace]
        op = proposal.operation
        stdin: str | None = None
        if op in (WriteOperation.CREATE, WriteOperation.APPLY):
            argv = [self._kubectl, "apply", "-f", "-", *ns, "-o", "name"]
            stdin = json.dumps(proposal.manifest)
        elif op == WriteOperation.PATCH:
            argv = [
                self._kubectl, "patch", proposal.resource_kind, proposal.name, *ns,
                "--type", "merge", "-p", json.dumps(proposal.patch),
            ]
        elif op == WriteOperation.SCALE:
            argv = [
                self._kubectl, "scale", f"{proposal.resource_kind}/{proposal.name}", *ns,
                f"--replicas={proposal.replicas}",
            ]
        elif op == WriteOperation.DELETE:
            argv = [self._kubectl, "delete", proposal.resource_kind, proposal.name, *ns]
        else:  # pragma: no cover - enum is exhaustive
            raise ApplyError(f"unsupported operation {op!r}")

        if dry_run:
            # scale has no server dry-run; fall back to a client-side echo.
            argv.append("--dry-run=server" if op != WriteOperation.SCALE else "--dry-run=client")
        return argv, stdin

    def _run(self, proposal: WriteProposal, dry_run: bool) -> str:
        argv, stdin = self._argv(proposal, dry_run)
        try:
            proc = subprocess.run(  # noqa: S603 - argv is built from a validated proposal
                argv, input=stdin, capture_output=True, text=True, timeout=self._timeout
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
            raise ApplyError(f"kubectl timed out after {self._timeout}s") from exc
        except FileNotFoundError as exc:
            raise ApplyError(f"kubectl binary not found: {self._kubectl}") from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            denied = "forbidden" in err.lower() or "cannot " in err.lower()
            raise ApplyError(err or f"kubectl exited {proc.returncode}", denied=denied)
        return (proc.stdout or proc.stderr or "ok").strip()


class WriteGate:
    """Holds pending proposals and is the only path from proposal to execution.

    A proposal can only ever leave PENDING through ``approve`` (which runs the
    applier) or ``reject`` — both of which require an out-of-band human call.
    Approval is single-use and TTL-bounded.
    """

    def __init__(
        self,
        applier: Applier,
        *,
        allowed_namespace: str,
        ttl_seconds: int,
        audit: AuditSink | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._applier = applier
        self._allowed_ns = allowed_namespace
        self._ttl = ttl_seconds
        self._audit = audit or LoggingAuditSink()
        self._clock = clock
        self._store: dict[str, WriteProposal] = {}

    # -- proposal creation (called by the LLM's non-mutating tool) ------------
    def propose(
        self,
        *,
        operation: str,
        resource_kind: str,
        namespace: str,
        rationale: str,
        name: str | None = None,
        manifest: dict | None = None,
        patch: dict | None = None,
        replicas: int | None = None,
        session_id: str | None = None,
    ) -> WriteProposal:
        """Record a pending write and compute its dry-run preview. Never mutates."""
        if namespace != self._allowed_ns:
            # Refused before it is even stored — the app-level twin of RBAC.
            denied = WriteProposal(
                id=self._token(), operation=WriteOperation(operation), resource_kind=resource_kind,
                namespace=namespace, name=name, manifest=manifest, patch=patch, replicas=replicas,
                rationale=rationale, session_id=session_id, status=ProposalStatus.DENIED,
                outcome=f"namespace '{namespace}' is out of scope; only '{self._allowed_ns}' is writable.",
            )
            self._audit_event("denied", denied)
            return denied

        proposal = WriteProposal(
            id=self._token(), operation=WriteOperation(operation), resource_kind=resource_kind,
            namespace=namespace, name=name, manifest=manifest, patch=patch, replicas=replicas,
            rationale=rationale, session_id=session_id, created_at=self._clock(),
        )
        try:
            proposal.preview = self._applier.preview(proposal)
        except ApplyError as exc:
            # A failed dry-run is useful signal — keep the proposal pending but
            # surface the error so the human can judge (or reject) it.
            proposal.preview = f"(dry-run failed) {exc}"
        self._store[proposal.id] = proposal
        self._audit_event("proposed", proposal)
        return proposal

    # -- human decisions ------------------------------------------------------
    def approve(self, token: str, approver: str) -> WriteProposal:
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

    def reject(self, token: str, approver: str) -> WriteProposal:
        proposal = self._require_pending(token)
        proposal.approver = approver
        proposal.status = ProposalStatus.REJECTED
        proposal.outcome = "rejected by approver; no change made."
        self._audit_event("rejected", proposal)
        return proposal

    # -- lookups --------------------------------------------------------------
    def get(self, token: str) -> WriteProposal | None:
        proposal = self._store.get(token)
        if proposal and proposal.status == ProposalStatus.PENDING and self._expired(proposal):
            proposal.status = ProposalStatus.EXPIRED
            self._audit_event("expired", proposal)
        return proposal

    def pending_for_session(self, session_id: str) -> list[WriteProposal]:
        return [
            p for p in self._store.values()
            if p.session_id == session_id and p.status == ProposalStatus.PENDING and not self._expired(p)
        ]

    # -- internals ------------------------------------------------------------
    def _require_pending(self, token: str) -> WriteProposal:
        proposal = self._store.get(token)
        if proposal is None:
            raise KeyError(f"no such proposal '{token}'")
        if self._expired(proposal) and proposal.status == ProposalStatus.PENDING:
            proposal.status = ProposalStatus.EXPIRED
            self._audit_event("expired", proposal)
        if proposal.is_terminal():
            raise ValueError(f"proposal '{token}' is already {proposal.status.value}; single-use.")
        return proposal

    def _expired(self, proposal: WriteProposal) -> bool:
        return (self._clock() - proposal.created_at) > self._ttl

    def _token(self) -> str:
        return f"pw_{secrets.token_hex(4)}"

    def _audit_event(self, event: str, proposal: WriteProposal) -> None:
        self._audit.record(
            {
                "event": event,
                "ts": self._clock(),
                "proposal_id": proposal.id,
                "operation": proposal.operation.value,
                "target": proposal.human_summary(),
                "namespace": proposal.namespace,
                "status": proposal.status.value,
                "approver": proposal.approver,
                "session_id": proposal.session_id,
                "outcome": proposal.outcome,
            }
        )

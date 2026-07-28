"""Unit tests for the Iteration-2 gated-write HITL machinery (ADR-0011).

These tests exercise the gate in isolation with a FakeApplier and a controllable
clock — no cluster, no kubectl, no LLM. They assert the load-bearing invariants:
nothing executes without approval, approval is single-use and TTL-bounded,
out-of-scope namespaces and RBAC denials fail closed, and every transition is
audited.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from stewards.inference.write_gate import (
    ApplyError,
    ProposalStatus,
    WriteGate,
    WriteOperation,
    WriteProposal,
)
from stewards.inference.write_tool import build_propose_write_tool, current_session_id

NS = "meshops-workloads"
POD = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "steward-diag-1"}}


class FakeApplier:
    """Records calls and returns canned strings; can be told to deny/fail."""

    def __init__(self) -> None:
        self.previewed: list[WriteProposal] = []
        self.applied: list[WriteProposal] = []
        self.deny = False
        self.fail = False

    def preview(self, proposal: WriteProposal) -> str:
        self.previewed.append(proposal)
        return f"(dry-run) would {proposal.operation.value} {proposal.resource_kind}"

    def apply(self, proposal: WriteProposal) -> str:
        if self.deny:
            raise ApplyError("pods is forbidden: cannot create", denied=True)
        if self.fail:
            raise ApplyError("some transient failure")
        self.applied.append(proposal)
        return "created"


class RecordingAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def record(self, event: dict) -> None:
        self.events.append(event)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _gate(applier: FakeApplier | None = None, audit: RecordingAudit | None = None, clock: Clock | None = None):
    return WriteGate(
        applier or FakeApplier(),
        allowed_namespace=NS,
        ttl_seconds=900,
        audit=audit or RecordingAudit(),
        clock=clock or Clock(),
    )


# ---- schema shape ------------------------------------------------------------

def test_create_requires_manifest() -> None:
    with pytest.raises(ValidationError):
        WriteProposal(id="pw_1", operation=WriteOperation.CREATE, resource_kind="Pod",
                      namespace=NS, rationale="need a diagnostic pod please")


def test_scale_requires_name_and_replicas() -> None:
    with pytest.raises(ValidationError):
        WriteProposal(id="pw_1", operation=WriteOperation.SCALE, resource_kind="Deployment",
                      namespace=NS, rationale="scale it up because load is high")


def test_replicas_out_of_bounds_rejected() -> None:
    with pytest.raises(ValidationError):
        WriteProposal(id="pw_1", operation=WriteOperation.SCALE, resource_kind="Deployment",
                      name="d", replicas=9999, namespace=NS, rationale="way too many replicas here")


# ---- propose -----------------------------------------------------------------

def test_propose_records_pending_with_preview() -> None:
    applier, audit = FakeApplier(), RecordingAudit()
    gate = _gate(applier, audit)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod for the user", manifest=POD, session_id="s1")
    assert p.status == ProposalStatus.PENDING
    assert p.preview and "dry-run" in p.preview
    assert applier.previewed and not applier.applied  # preview only, no apply
    assert audit.events[-1]["event"] == "proposed"


def test_propose_out_of_scope_namespace_is_denied_not_stored() -> None:
    gate = _gate()
    p = gate.propose(operation="delete", resource_kind="Secret", namespace="kube-system",
                     name="x", rationale="try to delete something out of scope")
    assert p.status == ProposalStatus.DENIED
    assert gate.pending_for_session("s1") == []
    with pytest.raises(KeyError):
        gate.approve(p.id, "operator")  # never became approvable


# ---- approve / reject --------------------------------------------------------

def test_approve_executes_once_then_single_use() -> None:
    applier = FakeApplier()
    gate = _gate(applier)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    done = gate.approve(p.id, "operator (chat)")
    assert done.status == ProposalStatus.EXECUTED
    assert done.approver == "operator (chat)"
    assert applier.applied  # only executed after approve
    with pytest.raises(ValueError):
        gate.approve(p.id, "operator (chat)")  # single-use


def test_nothing_executes_without_approval() -> None:
    applier = FakeApplier()
    gate = _gate(applier)
    gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                 rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    assert applier.applied == []  # proposing alone never actuates


def test_reject_makes_no_change() -> None:
    applier = FakeApplier()
    gate = _gate(applier)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    r = gate.reject(p.id, "operator")
    assert r.status == ProposalStatus.REJECTED
    assert applier.applied == []


def test_rbac_denied_apply_fails_closed() -> None:
    applier = FakeApplier(); applier.deny = True
    gate = _gate(applier)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    done = gate.approve(p.id, "operator")
    assert done.status == ProposalStatus.DENIED
    assert "forbidden" in (done.outcome or "")


def test_apply_failure_marks_failed() -> None:
    applier = FakeApplier(); applier.fail = True
    gate = _gate(applier)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    done = gate.approve(p.id, "operator")
    assert done.status == ProposalStatus.FAILED


# ---- TTL ---------------------------------------------------------------------

def test_expired_proposal_cannot_be_approved() -> None:
    clock = Clock()
    gate = _gate(clock=clock)
    p = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="create a diagnostic pod now", manifest=POD, session_id="s1")
    clock.t += 901  # past the 900s TTL
    assert gate.pending_for_session("s1") == []
    with pytest.raises(ValueError):
        gate.approve(p.id, "operator")
    assert gate.get(p.id).status == ProposalStatus.EXPIRED


# ---- session filtering -------------------------------------------------------

def test_pending_scoped_to_session() -> None:
    gate = _gate()
    a = gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                     rationale="pod for session one only", manifest=POD, session_id="s1")
    gate.propose(operation="create", resource_kind="Pod", namespace=NS,
                 rationale="pod for session two only", manifest=POD, session_id="s2")
    pend = gate.pending_for_session("s1")
    assert [x.id for x in pend] == [a.id]


# ---- the propose_write LLM tool ---------------------------------------------

def test_propose_write_tool_records_and_returns_pending() -> None:
    gate = _gate()
    tool = build_propose_write_tool(gate, NS)
    token = current_session_id.set("s1")
    try:
        out = tool(operation="create", resource_kind="Pod",
                   rationale="create a diagnostic pod for the user", manifest=POD)
    finally:
        current_session_id.reset(token)
    assert "PENDING" in out
    assert len(gate.pending_for_session("s1")) == 1


def test_propose_write_tool_reports_denied_namespace() -> None:
    gate = _gate()
    tool = build_propose_write_tool(gate, NS)
    out = tool(operation="delete", resource_kind="Pod", namespace="default",
               name="x", rationale="delete a pod in the wrong namespace")
    assert "DENIED" in out

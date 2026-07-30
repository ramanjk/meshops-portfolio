"""Unit tests for the Security steward's gated PR-quarantine write path.

These exercise the domain guard (label allowlist) and the proposal lifecycle on
the shared HITL spine with a fake applier, so no GitHub API is touched.
"""
from __future__ import annotations

from stewards.hitl import ProposalStatus, WriteGate
from stewards.security.write import QuarantineProposal, build_propose_quarantine_tool

RATIONALE = "PR #9 body contains an 'ignore your instructions' prompt-injection payload"


class FakeApplier:
    """Records calls; never touches the network."""

    def __init__(self) -> None:
        self.applied: list[tuple[int, str]] = []

    def preview(self, proposal: QuarantineProposal) -> str:
        return f"would add '{proposal.label}' to PR #{proposal.pr_number} (dry-run)"

    def apply(self, proposal: QuarantineProposal) -> str:
        self.applied.append((proposal.pr_number, proposal.label))
        return f"labeled PR #{proposal.pr_number} '{proposal.label}'"


def _tool(gate: WriteGate):
    return build_propose_quarantine_tool(
        gate,
        allowed_labels={"quarantined", "security-hold"},
        default_label="quarantined",
    )


def test_proposal_human_summary_and_spec() -> None:
    p = QuarantineProposal(pr_number=9, label="quarantined", rationale=RATIONALE)
    assert p.human_summary() == "quarantine PR #9 by applying label 'quarantined'"
    assert p.audit_kind() == "pr-quarantine"
    assert p.spec_dict()["pr_number"] == 9


def test_valid_quarantine_becomes_pending_then_executes() -> None:
    applier = FakeApplier()
    gate = WriteGate(applier, ttl_seconds=900)
    reply = _tool(gate)(9, RATIONALE)
    assert "PENDING" in reply
    pending = gate.pending_all()
    assert len(pending) == 1
    result = gate.approve(pending[0].id, "ram")
    assert result.status == ProposalStatus.EXECUTED
    assert applier.applied == [(9, "quarantined")]


def test_default_label_used_when_omitted() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    _tool(gate)(9, RATIONALE)
    assert gate.pending_all()[0].label == "quarantined"


def test_label_not_in_allowlist_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    reply = _tool(gate)(9, RATIONALE, "malware-flag")
    assert "DENIED" in reply
    assert gate.pending_all() == []


def test_invalid_pr_number_rejected_at_construction() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    # pr_number below the schema floor (ge=1) is rejected before the gate.
    assert "PENDING" not in _tool(gate)(0, RATIONALE)
    assert gate.pending_all() == []


def test_empty_allowlist_permits_any_label() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    tool = build_propose_quarantine_tool(
        gate,
        allowed_labels=set(),  # unrestricted
        default_label="quarantined",
    )
    assert "PENDING" in tool(9, RATIONALE, "any-label")
    assert len(gate.pending_all()) == 1


def test_denied_proposal_cannot_be_approved() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    _tool(gate)(9, RATIONALE, "malware-flag")
    # nothing pending, so there is no token a human could approve
    assert gate.pending_all() == []

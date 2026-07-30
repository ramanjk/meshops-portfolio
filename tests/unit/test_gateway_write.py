"""Unit tests for the Gateway steward's gated per-route budget-cap write path.

These exercise the domain guard (route allowlist / budget bounds) and the
proposal lifecycle on the shared HITL spine with a fake applier, so no cluster or
kubectl binary is touched.
"""
from __future__ import annotations

from stewards.gateway.write import BudgetProposal, build_propose_budget_tool
from stewards.hitl import ProposalStatus, WriteGate

RATIONALE = "the economy lane is throttling under load; raise its cap"


class FakeApplier:
    """Records calls; never shells out."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, float]] = []

    def preview(self, proposal: BudgetProposal) -> str:
        return f"budget ? -> ${proposal.budget:.2f} (dry-run)"

    def apply(self, proposal: BudgetProposal) -> str:
        self.applied.append((proposal.route, proposal.budget))
        return f"set {proposal.route} budget to ${proposal.budget:.2f}"


def _tool(gate: WriteGate):
    return build_propose_budget_tool(
        gate,
        allowed_routes={"chat-economy", "chat-premium"},
        min_budget=0.0,
        max_budget=100.0,
    )


def test_proposal_human_summary_and_spec() -> None:
    p = BudgetProposal(route="chat-economy", budget=12.0, rationale=RATIONALE)
    assert p.human_summary() == "set budget cap of route 'chat-economy' to $12.00"
    assert p.audit_kind() == "route-budget"
    assert p.spec_dict()["max_budget"] == 12.0


def test_valid_budget_becomes_pending_then_executes() -> None:
    applier = FakeApplier()
    gate = WriteGate(applier, ttl_seconds=900)
    reply = _tool(gate)("chat-economy", 12.0, RATIONALE)
    assert "PENDING" in reply
    pending = gate.pending_all()
    assert len(pending) == 1
    result = gate.approve(pending[0].id, "ram")
    assert result.status == ProposalStatus.EXECUTED
    assert applier.applied == [("chat-economy", 12.0)]


def test_route_not_in_allowlist_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    reply = _tool(gate)("chat-vip", 12.0, RATIONALE)
    assert "DENIED" in reply
    assert gate.pending_all() == []


def test_budget_out_of_range_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    # Above the configured max is caught by the domain guard (DENIED); below the
    # schema floor (ge=0) is caught even earlier at construction (REJECTED).
    # Both are non-recorded and non-approvable — the point is nothing pends.
    assert "PENDING" not in _tool(gate)("chat-economy", 999.0, RATIONALE)
    assert "PENDING" not in _tool(gate)("chat-economy", -1.0, RATIONALE)
    assert gate.pending_all() == []


def test_empty_allowlist_permits_any_route() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    tool = build_propose_budget_tool(
        gate,
        allowed_routes=set(),  # unrestricted
        min_budget=0.0,
        max_budget=100.0,
    )
    assert "PENDING" in tool("any-route", 20.0, RATIONALE)
    assert len(gate.pending_all()) == 1


def test_denied_proposal_cannot_be_approved() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    _tool(gate)("chat-economy", 999.0, RATIONALE)
    # nothing pending, so there is no token a human could approve
    assert gate.pending_all() == []

"""Unit tests for the SRE steward's gated Deployment-scale write path.

These exercise the domain guard (namespace / allowlist / replica bounds) and the
proposal lifecycle on the shared HITL spine with a fake applier, so no cluster or
kubectl binary is touched.
"""
from __future__ import annotations

from stewards.hitl import ProposalStatus, WriteGate
from stewards.sre.write import ScaleProposal, build_propose_scale_tool

RATIONALE = "sustained saturation observed on the workload"


class FakeApplier:
    """Records calls; never shells out."""

    def __init__(self) -> None:
        self.applied: list[tuple[str, int]] = []

    def preview(self, proposal: ScaleProposal) -> str:
        return f"replicas ? -> {proposal.replicas} (dry-run)"

    def apply(self, proposal: ScaleProposal) -> str:
        self.applied.append((proposal.deployment, proposal.replicas))
        return f"scaled {proposal.deployment} to {proposal.replicas}"


def _tool(gate: WriteGate):
    return build_propose_scale_tool(
        gate,
        allowed_namespace="meshops-workloads",
        allowed_deployments={"demo-web"},
        min_replicas=0,
        max_replicas=5,
    )


def test_proposal_human_summary_and_spec() -> None:
    p = ScaleProposal(
        namespace="meshops-workloads", deployment="demo-web", replicas=3, rationale=RATIONALE
    )
    assert p.human_summary() == "scale Deployment/demo-web in ns/meshops-workloads to 3 replica(s)"
    assert p.audit_kind() == "deployment-scale"
    assert p.spec_dict()["replicas"] == 3


def test_valid_scale_becomes_pending_then_executes() -> None:
    applier = FakeApplier()
    gate = WriteGate(applier, ttl_seconds=900)
    reply = _tool(gate)("demo-web", 3, RATIONALE)
    assert "PENDING" in reply
    pending = gate.pending_all()
    assert len(pending) == 1
    result = gate.approve(pending[0].id, "ram")
    assert result.status == ProposalStatus.EXECUTED
    assert applier.applied == [("demo-web", 3)]


def test_out_of_scope_namespace_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    reply = _tool(gate)("demo-web", 3, RATIONALE, namespace="default")
    assert "DENIED" in reply
    assert gate.pending_all() == []


def test_deployment_not_in_allowlist_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    reply = _tool(gate)("other-app", 3, RATIONALE)
    assert "DENIED" in reply
    assert gate.pending_all() == []


def test_replicas_out_of_range_denied() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    # Above the configured max is caught by the domain guard (DENIED); below the
    # schema floor (ge=0) is caught even earlier at construction (REJECTED).
    # Both are non-recorded and non-approvable — the point is nothing pends.
    assert "PENDING" not in _tool(gate)("demo-web", 99, RATIONALE)
    assert "PENDING" not in _tool(gate)("demo-web", -1, RATIONALE)
    assert gate.pending_all() == []


def test_empty_allowlist_permits_any_deployment_in_namespace() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    tool = build_propose_scale_tool(
        gate,
        allowed_namespace="meshops-workloads",
        allowed_deployments=set(),  # unrestricted within the namespace
        min_replicas=0,
        max_replicas=5,
    )
    assert "PENDING" in tool("anything", 2, RATIONALE)
    assert len(gate.pending_all()) == 1


def test_denied_proposal_cannot_be_approved() -> None:
    gate = WriteGate(FakeApplier(), ttl_seconds=900)
    _tool(gate)("demo-web", 99, RATIONALE)
    # nothing pending, so there is no token a human could approve
    assert gate.pending_all() == []

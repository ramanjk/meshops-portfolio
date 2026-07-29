"""Unit tests for the shared HITL gate + channels (ADR-0011), plus the pipeline
and quality domain appliers/tools.

Everything runs in isolation with fakes and a controllable clock — no cluster,
no MLflow, no Langfuse, no LLM. We assert the load-bearing invariants: nothing
executes without approval, approval is single-use and TTL-bounded, denials fail
closed, every transition is audited, and each domain's propose tool records a
proposal without ever actuating.
"""
from __future__ import annotations

import pytest

from stewards.hitl.channels import (
    GitHubPRChannel,
    PRRef,
    PRStatus,
)
from stewards.hitl.gate import (
    ApplyError,
    LoggingAuditSink,
    Proposal,
    ProposalStatus,
    WriteGate,
)
from stewards.hitl.session import current_session_id
from stewards.pipeline.write import (
    MlflowApplier,
    PromotionProposal,
    build_propose_promotion_tool,
)
from stewards.quality.write import (
    AnnotationProposal,
    LangfuseApplier,
    build_propose_annotation_tool,
)


# --------------------------------------------------------------------------- #
# A trivial domain proposal + applier to exercise the generic gate directly.
# --------------------------------------------------------------------------- #

class _DemoProposal(Proposal):
    target: str

    def human_summary(self) -> str:
        return f"touch {self.target}"

    def spec_dict(self) -> dict:
        return {"target": self.target}


class _FakeApplier:
    def __init__(self) -> None:
        self.previewed: list[Proposal] = []
        self.applied: list[Proposal] = []
        self.deny = False
        self.fail = False

    def preview(self, proposal: Proposal) -> str:
        self.previewed.append(proposal)
        return f"(dry-run) {proposal.human_summary()}"

    def apply(self, proposal: Proposal) -> str:
        if self.deny:
            raise ApplyError("forbidden", denied=True)
        if self.fail:
            raise ApplyError("boom")
        self.applied.append(proposal)
        return f"applied {proposal.id}"


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


def _gate(applier=None, ttl=900, clock=None):
    return WriteGate(applier or _FakeApplier(), ttl_seconds=ttl, clock=clock or _Clock())


def _submit(gate, target="thing", session_id="s1"):
    return gate.submit(_DemoProposal(target=target, rationale="because tests", session_id=session_id))


# --------------------------------------------------------------------------- #
# Gate invariants
# --------------------------------------------------------------------------- #

def test_submit_previews_but_does_not_apply():
    applier = _FakeApplier()
    gate = _gate(applier)
    p = _submit(gate)
    assert p.status == ProposalStatus.PENDING
    assert p.id.startswith("pw_")
    assert applier.previewed and not applier.applied  # dry-run only


def test_nothing_executes_without_approval():
    applier = _FakeApplier()
    gate = _gate(applier)
    _submit(gate)
    assert applier.applied == []


def test_approve_executes_once_and_is_single_use():
    applier = _FakeApplier()
    gate = _gate(applier)
    p = _submit(gate)
    out = gate.approve(p.id, "ram")
    assert out.status == ProposalStatus.EXECUTED
    assert out.approver == "ram"
    assert len(applier.applied) == 1
    with pytest.raises(ValueError):
        gate.approve(p.id, "ram")  # single-use


def test_reject_never_applies():
    applier = _FakeApplier()
    gate = _gate(applier)
    p = _submit(gate)
    out = gate.reject(p.id, "ram")
    assert out.status == ProposalStatus.REJECTED
    assert applier.applied == []


def test_denied_apply_fails_closed():
    applier = _FakeApplier()
    applier.deny = True
    gate = _gate(applier)
    p = _submit(gate)
    out = gate.approve(p.id, "ram")
    assert out.status == ProposalStatus.DENIED


def test_failed_apply_marked_failed():
    applier = _FakeApplier()
    applier.fail = True
    gate = _gate(applier)
    p = _submit(gate)
    out = gate.approve(p.id, "ram")
    assert out.status == ProposalStatus.FAILED


def test_ttl_expiry_blocks_approval():
    clock = _Clock()
    gate = _gate(ttl=60, clock=clock)
    p = _submit(gate)
    clock.t += 61
    assert gate.pending_for_session("s1") == []
    with pytest.raises(ValueError):
        gate.approve(p.id, "ram")


def test_deny_guard_records_but_never_stores_pending():
    gate = _gate()
    denied = gate.deny(_DemoProposal(target="x", rationale="nope not allowed"), "out of scope")
    assert denied.status == ProposalStatus.DENIED
    assert gate.pending_all() == []


def test_pending_for_session_scopes_by_session():
    gate = _gate()
    _submit(gate, session_id="a")
    _submit(gate, session_id="b")
    assert len(gate.pending_for_session("a")) == 1
    assert len(gate.pending_for_session("b")) == 1


def test_audit_sink_records_events(caplog):
    import logging

    gate = WriteGate(_FakeApplier(), ttl_seconds=900, clock=_Clock(), audit=LoggingAuditSink())
    with caplog.at_level(logging.INFO, logger="meshops.hitl.audit"):
        p = _submit(gate)
        gate.approve(p.id, "ram")
    joined = " ".join(r.message for r in caplog.records)
    assert "proposed" in joined and "executed" in joined


# --------------------------------------------------------------------------- #
# GitHub PR channel (with a fake client) — generic over any Proposal
# --------------------------------------------------------------------------- #

class _FakeGitHub:
    def __init__(self) -> None:
        self.created: list[dict] = []
        self._status = PRStatus(state="open", merged=False, decided_by=None)

    def create_pr(self, *, branch, base, title, body, path, content) -> PRRef:
        self.created.append({"branch": branch, "title": title, "path": path})
        return PRRef(number=7, url="https://example/pr/7")

    def pr_status(self, number: int) -> PRStatus:
        return self._status


def test_pr_channel_opens_and_reconciles_merge():
    gh = _FakeGitHub()
    ch = GitHubPRChannel(gh, base_branch="main", proposals_dir="hitl-proposals")
    gate = _gate()
    p = _submit(gate)
    ch.open(p)
    assert p.external_id == "7" and p.external_ref.endswith("/pr/7")
    assert gh.created[0]["path"].endswith(".md")
    gh._status = PRStatus(state="closed", merged=True, decided_by="ramanjk")
    changed = ch.sync(gate)
    assert len(changed) == 1 and changed[0].status == ProposalStatus.EXECUTED
    assert changed[0].approver == "ramanjk"


def test_pr_channel_close_rejects():
    gh = _FakeGitHub()
    ch = GitHubPRChannel(gh, base_branch="main", proposals_dir="hitl-proposals")
    gate = _gate()
    p = _submit(gate)
    ch.open(p)
    gh._status = PRStatus(state="closed", merged=False, decided_by=None)
    changed = ch.sync(gate)
    assert changed[0].status == ProposalStatus.REJECTED


# --------------------------------------------------------------------------- #
# Pipeline domain: PromotionProposal + MlflowApplier + propose_promotion tool
# --------------------------------------------------------------------------- #

def test_promotion_proposal_summary_and_spec():
    p = PromotionProposal(model_name="m", version=3, to_stage="Production", rationale="higher acc")
    assert "v3" in p.human_summary() and "Production" in p.human_summary()
    assert p.spec_dict()["version"] == 3
    assert p.audit_kind() == "registry-promotion"


def test_mlflow_applier_guards_foreign_model():
    applier = MlflowApplier("http://mlflow", "phi-4-mini-meshops")
    p = PromotionProposal(model_name="other", version=1, to_stage="Staging", rationale="foreign model attempt")
    with pytest.raises(ApplyError) as exc:
        applier.preview(p)
    assert exc.value.denied


def test_propose_promotion_tool_records_pending():
    gate = _gate()
    tool = build_propose_promotion_tool(gate, "phi-4-mini-meshops")
    token = current_session_id.set("s9")
    try:
        out = tool(version=3, to_stage="Production", rationale="v3 scores higher than prod")
    finally:
        current_session_id.reset(token)
    assert "PENDING" in out
    pend = gate.pending_for_session("s9")
    assert len(pend) == 1 and isinstance(pend[0], PromotionProposal)


def test_propose_promotion_tool_rejects_bad_stage():
    gate = _gate()
    tool = build_propose_promotion_tool(gate, "phi-4-mini-meshops")
    out = tool(version=3, to_stage="Prod", rationale="typo stage here")
    assert "REJECTED" in out
    assert gate.pending_all() == []


# --------------------------------------------------------------------------- #
# Quality domain: AnnotationProposal + LangfuseApplier + propose_annotation tool
# --------------------------------------------------------------------------- #

def test_annotation_proposal_summary_and_spec():
    p = AnnotationProposal(
        trace_id="abcd1234ef", score_name="human_review", score_value=0.2, rationale="low quality"
    )
    assert "human_review=0.2" in p.human_summary()
    assert p.spec_dict()["trace_id"] == "abcd1234ef"
    assert p.audit_kind() == "trace-annotation"


def test_annotation_value_bounds_enforced():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AnnotationProposal(
            trace_id="abcd1234ef", score_name="x", score_value=1.5, rationale="out of range"
        )


def test_propose_annotation_tool_records_pending():
    gate = _gate()
    tool = build_propose_annotation_tool(gate)
    token = current_session_id.set("q1")
    try:
        out = tool(
            trace_id="abcd1234ef99", score_name="human_review", score_value=0.2,
            rationale="flagging a low-quality answer",
        )
    finally:
        current_session_id.reset(token)
    assert "PENDING" in out
    pend = gate.pending_for_session("q1")
    assert len(pend) == 1 and isinstance(pend[0], AnnotationProposal)


def test_propose_annotation_tool_rejects_bad_value():
    gate = _gate()
    tool = build_propose_annotation_tool(gate)
    out = tool(trace_id="abcd1234ef", score_name="x", score_value=9.0, rationale="way too high val")
    assert "REJECTED" in out
    assert gate.pending_all() == []

"""Unit tests for the pluggable HITL approval channels (ADR-0011).

The GitHub-PR channel is exercised with a FakeGitHubClient — no live GitHub, no
`gh` CLI, no network. We assert the load-bearing behaviours: opening a proposal
publishes a PR and records its external ref; merging the PR reconciles to an
executed write; closing it reconciles to a rejection; and the sync loop is
idempotent (a resolved proposal is never touched again). The chat channel is a
verified no-op.
"""
from __future__ import annotations

from stewards.inference.approval_channels import (
    ChatApprovalChannel,
    GitHubPRChannel,
    PRRef,
    PRStatus,
)
from stewards.inference.write_gate import ProposalStatus, WriteGate, WriteProposal

NS = "meshops-workloads"
POD = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "steward-diag-1"}}


class FakeApplier:
    def __init__(self) -> None:
        self.applied: list[WriteProposal] = []

    def preview(self, proposal: WriteProposal) -> str:
        return "(dry-run) ok"

    def apply(self, proposal: WriteProposal) -> str:
        self.applied.append(proposal)
        return "created"


class FakeGitHubClient:
    """In-memory GitHub: create_pr stores a PR; tests flip its state."""

    def __init__(self) -> None:
        self.prs: dict[int, PRStatus] = {}
        self.created: list[dict] = []
        self._next = 41

    def create_pr(self, *, branch, base, title, body, path, content) -> PRRef:  # noqa: ANN001
        self._next += 1
        number = self._next
        self.created.append(
            {"number": number, "branch": branch, "base": base, "title": title, "path": path, "body": body}
        )
        self.prs[number] = PRStatus(state="open", merged=False, decided_by=None)
        return PRRef(number=number, url=f"https://github.com/acme/repo/pull/{number}")

    def pr_status(self, number: int) -> PRStatus:
        return self.prs[number]

    # test helpers
    def merge(self, number: int, who: str = "alice") -> None:
        self.prs[number] = PRStatus(state="closed", merged=True, decided_by=who)

    def close(self, number: int) -> None:
        self.prs[number] = PRStatus(state="closed", merged=False, decided_by=None)


def _gate(applier: FakeApplier) -> WriteGate:
    return WriteGate(applier, allowed_namespace=NS, ttl_seconds=10_000)


def _propose(gate: WriteGate) -> WriteProposal:
    return gate.propose(
        operation="create", resource_kind="Pod", namespace=NS, manifest=POD,
        rationale="diagnostic pod requested by operator", session_id="s1",
    )


def test_chat_channel_is_noop() -> None:
    ch = ChatApprovalChannel()
    gate = _gate(FakeApplier())
    p = _propose(gate)
    ch.open(p)
    assert p.external_ref is None
    assert ch.sync(gate) == []


def test_open_publishes_pr_and_records_ref() -> None:
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    gate = _gate(FakeApplier())
    p = _propose(gate)

    ch.open(p)

    assert len(client.created) == 1
    assert client.created[0]["branch"] == f"hitl/{p.id}"
    assert client.created[0]["path"] == f"hitl/{p.id}.md"
    assert p.external_id == str(client.created[0]["number"])
    assert p.external_ref.endswith(str(client.created[0]["number"]))
    # The PR body carries the dry-run preview so the reviewer sees the effect.
    assert "dry-run" in client.created[0]["body"]


def test_merge_reconciles_to_executed() -> None:
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    applier = FakeApplier()
    gate = _gate(applier)
    p = _propose(gate)
    ch.open(p)
    number = int(p.external_id)

    client.merge(number, who="alice")
    changed = ch.sync(gate)

    assert [c.id for c in changed] == [p.id]
    assert gate.get(p.id).status == ProposalStatus.EXECUTED
    assert gate.get(p.id).approver == "alice"
    assert applier.applied  # the deterministic executor ran the write


def test_close_reconciles_to_rejected() -> None:
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    applier = FakeApplier()
    gate = _gate(applier)
    p = _propose(gate)
    ch.open(p)

    client.close(int(p.external_id))
    changed = ch.sync(gate)

    assert [c.id for c in changed] == [p.id]
    assert gate.get(p.id).status == ProposalStatus.REJECTED
    assert not applier.applied  # nothing was applied


def test_sync_is_idempotent() -> None:
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    applier = FakeApplier()
    gate = _gate(applier)
    p = _propose(gate)
    ch.open(p)
    client.merge(int(p.external_id))

    first = ch.sync(gate)
    second = ch.sync(gate)

    assert len(first) == 1
    assert second == []  # already terminal -> not touched again
    assert len(applier.applied) == 1  # applied exactly once


def test_open_still_pending_is_not_synced_until_decided() -> None:
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    gate = _gate(FakeApplier())
    p = _propose(gate)
    ch.open(p)

    assert ch.sync(gate) == []  # PR still open -> no decision yet
    assert gate.get(p.id).status == ProposalStatus.PENDING


def test_pending_all_skips_proposals_without_external_id() -> None:
    # A proposal never published (no PR opened) has no external_id; sync ignores it.
    client = FakeGitHubClient()
    ch = GitHubPRChannel(client, base_branch="main", proposals_dir="hitl")
    gate = _gate(FakeApplier())
    _propose(gate)  # not opened

    assert ch.sync(gate) == []

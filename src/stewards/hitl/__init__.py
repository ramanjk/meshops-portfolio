"""Shared, domain-agnostic gated-write HITL machinery (ADR-0011).

Distilled from the inference steward's Iteration-2 gate so the pipeline and
quality stewards reuse the *identical* propose → human-approve → deterministic-
apply → audit spine, differing only in their domain :class:`Proposal` and
:class:`Applier`. See :mod:`stewards.hitl.gate` for the invariant.
"""
from __future__ import annotations

from .channels import (
    ApprovalChannel,
    ChatApprovalChannel,
    GhCliClient,
    GitHubClient,
    GitHubPRChannel,
    PRRef,
    PRStatus,
    build_channel,
)
from .gate import (
    Applier,
    ApplyError,
    AuditSink,
    LoggingAuditSink,
    Proposal,
    ProposalStatus,
    WriteGate,
)
from .session import current_session_id

__all__ = [
    "Applier",
    "ApplyError",
    "ApprovalChannel",
    "AuditSink",
    "ChatApprovalChannel",
    "GhCliClient",
    "GitHubClient",
    "GitHubPRChannel",
    "LoggingAuditSink",
    "PRRef",
    "PRStatus",
    "Proposal",
    "ProposalStatus",
    "WriteGate",
    "build_channel",
    "current_session_id",
]

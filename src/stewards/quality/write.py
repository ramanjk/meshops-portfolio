"""Iteration-2 gated write for the Quality steward: annotate a trace's score.

The Quality steward observes LLM traces and eval scores in Langfuse. Its *one*
mutation is attaching a **numeric evaluation score** to a specific trace — e.g.
a human-in-the-loop flags a low-quality answer by writing a ``human_review``
score of 0.2 on that trace. This is the quality gate's write-back: a reviewed
judgement recorded next to the evidence, which downstream (the Pipeline steward)
can weigh before a promotion.

This module supplies the two domain pieces the shared HITL spine
(:mod:`stewards.hitl`) needs:

  * :class:`AnnotationProposal` — the intent (trace, score name, value, comment).
  * :class:`LangfuseApplier` — deterministic preview/apply against the Langfuse
    public REST API (``POST /api/public/scores``), bounded to the project the
    steward's Basic-auth credentials already scope it to.

The LLM only ever calls :func:`build_propose_annotation_tool`, which records a
proposal and returns ``PENDING``. It has no path to actuation (ADR-0011).
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import httpx
from pydantic import Field

from ..hitl import ApplyError, Proposal, ProposalStatus, WriteGate, current_session_id

LOG = logging.getLogger("meshops.hello-quality.write")


class AnnotationProposal(Proposal):
    """A proposed numeric evaluation score to attach to a Langfuse trace."""

    trace_id: str = Field(..., min_length=8)
    score_name: str = Field(..., min_length=1, max_length=64)
    score_value: float = Field(..., ge=0.0, le=1.0)
    comment: str | None = Field(None, max_length=500)

    def human_summary(self) -> str:
        short = self.trace_id[:12]
        return f"annotate trace {short}… with {self.score_name}={self.score_value}"

    def spec_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "score_name": self.score_name,
            "score_value": self.score_value,
            "comment": self.comment,
        }

    def audit_kind(self) -> str:
        return "trace-annotation"


def _as_annotation(proposal: Proposal) -> AnnotationProposal:
    if not isinstance(proposal, AnnotationProposal):
        raise ApplyError(f"expected an AnnotationProposal, got {type(proposal).__name__}")
    return proposal


class LangfuseApplier:
    """Deterministic executor that writes a score via the Langfuse public API.

    Bounded by the Basic-auth credentials (public/secret key) to a single
    Langfuse project — the backstop equivalent of scoped RBAC.
    """

    def __init__(
        self, host: str, public_key: str, secret_key: str, timeout_seconds: float = 15.0
    ) -> None:
        self._base = host.rstrip("/") + "/api/public"
        self._auth = httpx.BasicAuth(public_key, secret_key)
        self._timeout = timeout_seconds

    def _get_trace(self, trace_id: str) -> dict:
        with httpx.Client(timeout=self._timeout, auth=self._auth) as client:
            resp = client.get(f"{self._base}/traces/{trace_id}")
        if resp.status_code == 404:
            raise ApplyError(f"trace {trace_id} not found")
        if resp.status_code in (401, 403):
            raise ApplyError("Langfuse rejected the credentials", denied=True)
        resp.raise_for_status()
        return resp.json()

    def preview(self, proposal: Proposal) -> str:
        proposal = _as_annotation(proposal)
        try:
            trace = self._get_trace(proposal.trace_id)
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            raise ApplyError(f"could not read trace: {exc}") from exc
        name = trace.get("name", "?")
        return (
            f"trace {proposal.trace_id} ({name}): will attach NUMERIC score "
            f"'{proposal.score_name}'={proposal.score_value}. "
            f"No change made (dry-run)."
        )

    def apply(self, proposal: Proposal) -> str:
        proposal = _as_annotation(proposal)
        body: dict[str, object] = {
            "traceId": proposal.trace_id,
            "name": proposal.score_name,
            "value": proposal.score_value,
            "dataType": "NUMERIC",
        }
        if proposal.comment:
            body["comment"] = proposal.comment
        try:
            with httpx.Client(timeout=self._timeout, auth=self._auth) as client:
                resp = client.post(f"{self._base}/scores", json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            denied = exc.response.status_code in (401, 403)
            raise ApplyError(
                f"Langfuse rejected the score: {exc.response.text or exc}", denied=denied
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            raise ApplyError(f"Langfuse score write failed: {exc}") from exc
        score_id = resp.json().get("id", "(created)")
        return (
            f"score '{proposal.score_name}'={proposal.score_value} attached to "
            f"trace {proposal.trace_id} (score id {score_id})"
        )


def build_propose_annotation_tool(gate: WriteGate) -> Callable[..., str]:
    """Build the ``propose_annotation`` callable bound to ``gate`` for MAF to expose."""

    def propose_annotation(
        trace_id: str,
        score_name: str,
        score_value: float,
        rationale: str,
        comment: str | None = None,
    ) -> str:
        """Propose attaching a numeric eval score to a trace. Does NOT execute.

        Call this whenever the user asks to flag, annotate, rate, or score a
        specific trace (e.g. mark a low-quality answer for review). It records
        the proposal and returns a PENDING ticket. You MUST then show the user
        the proposal id and preview and ask them to approve or reject. NEVER
        claim the annotation was written — it has not been, and will not be,
        until the human approves.

        Args:
            trace_id: the Langfuse trace id to annotate (from the read tools).
            score_name: the score/metric name, e.g. "human_review".
            score_value: numeric value between 0.0 and 1.0.
            rationale: one sentence on why this annotation is being proposed.
            comment: optional free-text note stored alongside the score.

        Returns:
            A human-readable PENDING string with the proposal id and dry-run preview.
        """
        try:
            proposal = AnnotationProposal(
                trace_id=trace_id,
                score_name=score_name,
                score_value=score_value,
                comment=comment,
                rationale=rationale,
                session_id=current_session_id.get(),
            )
        except Exception as exc:
            LOG.warning("[write] propose rejected: %s", exc)
            return f"PROPOSAL REJECTED (not recorded): {exc}"

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

    return propose_annotation

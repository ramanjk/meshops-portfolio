"""Iteration-2 gated write for the Pipeline steward: registry stage promotion.

The Pipeline steward observes an MLflow Model Registry. Its *one* mutation is a
model-version **stage transition** (e.g. promote the Staging candidate to
Production) — the classic MLOps gate that UC-03 says must be human-approved.

This module supplies the two domain-specific pieces the shared HITL spine
(:mod:`stewards.hitl`) needs:

  * :class:`PromotionProposal` — the intent (which version, to which stage).
  * :class:`MlflowApplier` — deterministic preview/apply against the MLflow REST
    API 2.0 (``model-versions/transition-stage``). The applier is hard-bounded to
    a single registered model, so an approved-but-wrong proposal still cannot
    touch any other model — the backstop equivalent of the inference steward's
    namespaced RBAC Role.

The LLM only ever calls :func:`build_propose_promotion_tool`, which records a
proposal and returns ``PENDING``. It has no path to actuation (ADR-0011).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

import httpx
from pydantic import Field

from ..hitl import ApplyError, Proposal, ProposalStatus, WriteGate, current_session_id

LOG = logging.getLogger("meshops.hello-pipeline.write")

# The MLflow stages the gate understands. "None" is MLflow's un-staged state.
Stage = Literal["Staging", "Production", "Archived", "None"]
_VALID_STAGES = ("Staging", "Production", "Archived", "None")


class PromotionProposal(Proposal):
    """A proposed model-version stage transition in the MLflow registry."""

    model_name: str = Field(..., min_length=1)
    version: int = Field(..., ge=1)
    to_stage: Stage
    archive_existing: bool = Field(
        True,
        description="Archive whatever currently occupies to_stage (MLflow's "
        "archive_existing_versions) so a stage holds one version.",
    )

    def human_summary(self) -> str:
        return f"promote {self.model_name} v{self.version} → {self.to_stage}"

    def spec_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "version": self.version,
            "to_stage": self.to_stage,
            "archive_existing": self.archive_existing,
        }

    def audit_kind(self) -> str:
        return "registry-promotion"


def _as_promotion(proposal: Proposal) -> PromotionProposal:
    if not isinstance(proposal, PromotionProposal):
        raise ApplyError(f"expected a PromotionProposal, got {type(proposal).__name__}")
    return proposal


class MlflowApplier:
    """Deterministic executor for a stage transition via MLflow REST 2.0.

    Bounded to ``allowed_model``: any proposal naming another model is denied at
    both preview and apply, so the blast radius is a single registered model no
    matter what an approver clicks.
    """

    def __init__(self, tracking_uri: str, allowed_model: str, timeout_seconds: float = 15.0) -> None:
        self._base = tracking_uri.rstrip("/") + "/api/2.0/mlflow"
        self._allowed = allowed_model
        self._timeout = timeout_seconds

    def _get_version(self, name: str, version: int) -> dict:
        with httpx.Client(timeout=self._timeout) as client:
            resp = client.get(
                f"{self._base}/model-versions/get",
                params={"name": name, "version": str(version)},
            )
        if resp.status_code == 404:
            raise ApplyError(f"model version {name} v{version} not found")
        resp.raise_for_status()
        return resp.json().get("model_version", {})

    def _guard(self, proposal: PromotionProposal) -> None:
        if proposal.model_name != self._allowed:
            raise ApplyError(
                f"model '{proposal.model_name}' is out of scope; only "
                f"'{self._allowed}' is writable.",
                denied=True,
            )

    def preview(self, proposal: Proposal) -> str:
        proposal = _as_promotion(proposal)
        self._guard(proposal)
        try:
            mv = self._get_version(proposal.model_name, proposal.version)
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            raise ApplyError(f"could not read model version: {exc}") from exc
        current = mv.get("current_stage", "unknown")
        return (
            f"model-version {proposal.model_name} v{proposal.version}: "
            f"{current} → {proposal.to_stage} "
            f"(archive_existing={proposal.archive_existing}). "
            f"No change made (dry-run)."
        )

    def apply(self, proposal: Proposal) -> str:
        proposal = _as_promotion(proposal)
        self._guard(proposal)
        body = {
            "name": proposal.model_name,
            "version": str(proposal.version),
            "stage": proposal.to_stage,
            "archive_existing_versions": proposal.archive_existing,
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(f"{self._base}/model-versions/transition-stage", json=body)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            denied = exc.response.status_code in (401, 403)
            raise ApplyError(
                f"MLflow rejected the transition: {exc.response.text or exc}", denied=denied
            ) from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network dependent
            raise ApplyError(f"MLflow transition failed: {exc}") from exc
        stage = resp.json().get("model_version", {}).get("current_stage", proposal.to_stage)
        return f"{proposal.model_name} v{proposal.version} is now in stage {stage}"


def build_propose_promotion_tool(gate: WriteGate, allowed_model: str) -> Callable[..., str]:
    """Build the ``propose_promotion`` callable bound to ``gate`` for MAF to expose."""

    def propose_promotion(
        version: int,
        to_stage: str,
        rationale: str,
        archive_existing: bool = True,
    ) -> str:
        """Propose promoting a model version to a new registry stage. Does NOT execute.

        Call this whenever the user asks to promote, transition, roll back, or
        archive a version of the registered model. It records the proposal and
        returns a PENDING ticket. You MUST then show the user the proposal id and
        preview and ask them to approve or reject. NEVER claim the promotion was
        made — it has not been, and will not be, until the human approves.

        Args:
            version: the model version number to transition (integer ≥ 1).
            to_stage: target stage — one of "Staging", "Production", "Archived", "None".
            rationale: one sentence on why this promotion is being proposed.
            archive_existing: archive whatever currently holds to_stage (default true).

        Returns:
            A human-readable PENDING string with the proposal id and dry-run preview.
        """
        if to_stage not in _VALID_STAGES:
            return (
                f"PROPOSAL REJECTED (not recorded): to_stage must be one of "
                f"{', '.join(_VALID_STAGES)}; got {to_stage!r}."
            )
        try:
            proposal = PromotionProposal(
                model_name=allowed_model,
                version=version,
                to_stage=to_stage,  # type: ignore[arg-type]
                archive_existing=archive_existing,
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

    return propose_promotion

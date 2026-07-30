"""Iteration-2 gated write for the SRE steward: scale a Deployment's replicas.

The SRE steward correlates Prometheus + AKS + Langfuse into an incident picture.
Its *one* mutation is **changing the replica count of a Kubernetes Deployment** —
the "scaler-tuning" remediation from the agent catalog. When it concludes (and a
human agrees) that a workload is under- or over-provisioned, it proposes a scale;
a human approves; deterministic code runs ``kubectl scale`` under a namespaced
writer Role.

This module supplies the two domain pieces the shared HITL spine
(:mod:`stewards.hitl`) needs:

  * :class:`ScaleProposal` — the intent (namespace, deployment, replica count).
  * :class:`KubectlScaleApplier` — deterministic preview/apply that shells out to
    ``kubectl scale`` under the pod's bounded ServiceAccount token.

Three layers cap blast radius (defence-in-depth):
  1. persona — the read-only persona has no propose tool at all;
  2. domain guard — :func:`build_propose_scale_tool` rejects any target outside
     the allowed namespace / deployment allowlist / replica bounds *before* the
     gate stores it (recorded via :meth:`WriteGate.deny`, never approvable);
  3. RBAC — the writer Role is namespaced to ``scale_namespace`` and grants only
     ``deployments/scale``; an approved-but-wrong request is still capped.

The LLM only ever calls :func:`build_propose_scale_tool`, which records a
proposal and returns ``PENDING``. It has no path to actuation (ADR-0011).
"""
from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable

from pydantic import Field

from ..hitl import ApplyError, Proposal, ProposalStatus, WriteGate, current_session_id

LOG = logging.getLogger("meshops.hello-sre.write")


class ScaleProposal(Proposal):
    """A proposed replica-count change for one Kubernetes Deployment."""

    namespace: str = Field(..., min_length=1, max_length=63)
    deployment: str = Field(..., min_length=1, max_length=253)
    replicas: int = Field(..., ge=0, le=1000)

    def human_summary(self) -> str:
        return (
            f"scale Deployment/{self.deployment} in ns/{self.namespace} "
            f"to {self.replicas} replica(s)"
        )

    def spec_dict(self) -> dict:
        return {
            "kind": "Deployment",
            "namespace": self.namespace,
            "name": self.deployment,
            "replicas": self.replicas,
        }

    def audit_kind(self) -> str:
        return "deployment-scale"


def _as_scale(proposal: Proposal) -> ScaleProposal:
    if not isinstance(proposal, ScaleProposal):
        raise ApplyError(f"expected a ScaleProposal, got {type(proposal).__name__}")
    return proposal


class KubectlScaleApplier:
    """Deterministic executor: runs ``kubectl scale`` under the pod's bounded token.

    This is the same actuation aks-mcp's kubectl component performs; running it
    in-process from deterministic code (never the LLM) keeps the "model cannot
    actuate" invariant while the namespaced writer Role caps blast radius.
    """

    def __init__(self, kubectl_binary: str = "kubectl", timeout_seconds: int = 30) -> None:
        self._kubectl = kubectl_binary
        self._timeout = timeout_seconds

    def _current_replicas(self, proposal: ScaleProposal) -> int | None:
        argv = [
            self._kubectl, "get", "deployment", proposal.deployment,
            "-n", proposal.namespace, "-o", "jsonpath={.spec.replicas}",
        ]
        try:
            proc = subprocess.run(  # noqa: S603 - argv built from a validated proposal
                argv, capture_output=True, text=True, timeout=self._timeout
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):  # pragma: no cover - env dependent
            return None
        if proc.returncode != 0:
            return None
        out = (proc.stdout or "").strip()
        return int(out) if out.isdigit() else None

    def preview(self, proposal: Proposal) -> str:
        """Dry-run: read the current replica count and describe the delta.

        ``kubectl scale`` has no server-side dry-run, so we read the live count
        deterministically and report the intended transition. Reading also
        surfaces "deployment not found" / RBAC-forbidden errors before approval.
        """
        proposal = _as_scale(proposal)
        argv = [
            self._kubectl, "get", "deployment", proposal.deployment,
            "-n", proposal.namespace, "-o", "jsonpath={.spec.replicas}",
        ]
        try:
            proc = subprocess.run(  # noqa: S603 - argv built from a validated proposal
                argv, capture_output=True, text=True, timeout=self._timeout
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
            raise ApplyError(f"kubectl timed out after {self._timeout}s") from exc
        except FileNotFoundError as exc:
            raise ApplyError(f"kubectl binary not found: {self._kubectl}") from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            denied = "forbidden" in err.lower() or "cannot " in err.lower()
            raise ApplyError(err or f"kubectl exited {proc.returncode}", denied=denied)
        current = (proc.stdout or "").strip() or "?"
        return (
            f"Deployment/{proposal.deployment} in ns/{proposal.namespace}: "
            f"replicas {current} -> {proposal.replicas}. No change made (dry-run)."
        )

    def apply(self, proposal: Proposal) -> str:
        proposal = _as_scale(proposal)
        argv = [
            self._kubectl, "scale", f"deployment/{proposal.deployment}",
            "-n", proposal.namespace, f"--replicas={proposal.replicas}",
        ]
        try:
            proc = subprocess.run(  # noqa: S603 - argv built from a validated proposal
                argv, capture_output=True, text=True, timeout=self._timeout
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
            raise ApplyError(f"kubectl timed out after {self._timeout}s") from exc
        except FileNotFoundError as exc:
            raise ApplyError(f"kubectl binary not found: {self._kubectl}") from exc
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            denied = "forbidden" in err.lower() or "cannot " in err.lower()
            raise ApplyError(err or f"kubectl exited {proc.returncode}", denied=denied)
        return (
            f"scaled Deployment/{proposal.deployment} in ns/{proposal.namespace} "
            f"to {proposal.replicas} replica(s): {(proc.stdout or 'ok').strip()}"
        )


def build_propose_scale_tool(
    gate: WriteGate,
    *,
    allowed_namespace: str,
    allowed_deployments: set[str],
    min_replicas: int,
    max_replicas: int,
) -> Callable[..., str]:
    """Build the ``propose_scale`` callable bound to ``gate`` for MAF to expose.

    The domain guard (namespace / deployment allowlist / replica bounds) is
    enforced here, *before* the proposal is stored — a violating request is
    recorded via :meth:`WriteGate.deny` so it can never be approved.
    """

    def propose_scale(
        deployment: str,
        replicas: int,
        rationale: str,
        namespace: str | None = None,
    ) -> str:
        """Propose scaling a Deployment's replica count. Does NOT execute.

        Call this whenever the user asks to scale, resize, add/remove replicas,
        or otherwise change the replica count of a workload to remediate an
        incident. It records the proposal and returns a PENDING ticket. You MUST
        then show the user the proposal id and preview and ask them to approve or
        reject. NEVER claim the scale happened — it has not been, and will not
        be, until the human approves.

        Args:
            deployment: the Deployment name to scale (from the read tools).
            replicas: target replica count (a non-negative integer).
            rationale: one sentence on why this scale is being proposed.
            namespace: target namespace (defaults to the only writable namespace).

        Returns:
            A human-readable PENDING string with the proposal id and dry-run preview.
        """
        target_ns = namespace or allowed_namespace
        try:
            proposal = ScaleProposal(
                namespace=target_ns,
                deployment=deployment,
                replicas=replicas,
                rationale=rationale,
                session_id=current_session_id.get(),
            )
        except Exception as exc:  # surface validation errors to the LLM as text
            LOG.warning("[write] propose rejected: %s", exc)
            return f"PROPOSAL REJECTED (not recorded): {exc}"

        # --- domain guard: bound namespace / deployment / replica range -------
        guard_reason: str | None = None
        if target_ns != allowed_namespace:
            guard_reason = (
                f"namespace '{target_ns}' is out of scope; this steward may only "
                f"scale workloads in '{allowed_namespace}'."
            )
        elif allowed_deployments and deployment not in allowed_deployments:
            allowed = ", ".join(sorted(allowed_deployments))
            guard_reason = (
                f"Deployment '{deployment}' is not in the scale allowlist ({allowed})."
            )
        elif not (min_replicas <= replicas <= max_replicas):
            guard_reason = (
                f"replica count {replicas} is outside the allowed range "
                f"[{min_replicas}, {max_replicas}]."
            )
        if guard_reason is not None:
            proposal = gate.deny(proposal, guard_reason)
            return f"PROPOSAL DENIED: {guard_reason} No change was or will be made."

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

    return propose_scale

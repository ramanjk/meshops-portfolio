"""The single write-adjacent tool the LLM is allowed to hold: ``propose_write``.

Calling it does **not** touch the cluster. It records a pending proposal on the
``WriteGate`` and returns a ``PENDING`` string. The model therefore has no code
path to actuation — that is the first and most important defence in ADR-0011.

The current chat session id is carried on a ``ContextVar`` that the chat
endpoint sets before ``agent.run`` (function tools don't otherwise receive
session context), so a proposal can later be matched to its session and
surfaced as an approval card.
"""
from __future__ import annotations

import contextvars
import logging
from collections.abc import Callable

from .write_gate import ProposalStatus, WriteGate

LOG = logging.getLogger("meshops.hello-inference.write")

current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)


def build_propose_write_tool(gate: WriteGate, allowed_namespace: str) -> Callable[..., str]:
    """Build the ``propose_write`` callable bound to ``gate`` for MAF to expose."""

    def propose_write(
        operation: str,
        resource_kind: str,
        rationale: str,
        namespace: str | None = None,
        name: str | None = None,
        manifest: dict | None = None,
        patch: dict | None = None,
        replicas: int | None = None,
    ) -> str:
        """Propose a single cluster mutation for human approval. Does NOT execute.

        Call this whenever the user asks for ANY change to the cluster (create,
        apply, patch, scale, delete). It records the proposal and returns a
        PENDING ticket. You MUST then show the user the proposal id and preview
        and ask them to approve or reject. NEVER claim the change was made — it
        has not been, and will not be, until the human approves at the gate.

        Args:
            operation: one of "create", "apply", "patch", "scale", "delete".
            resource_kind: Kubernetes kind, e.g. "Pod", "Deployment", "Workspace".
            rationale: one sentence on why this change is being proposed.
            namespace: target namespace (defaults to the only writable namespace).
            name: resource name; required for patch/scale/delete.
            manifest: the full object (dict) for create/apply.
            patch: strategic-merge patch body (dict) for patch.
            replicas: target replica count for scale.

        Returns:
            A human-readable PENDING string with the proposal id and dry-run
            preview.
        """
        session_id = current_session_id.get()
        try:
            proposal = gate.propose(
                operation=operation,
                resource_kind=resource_kind,
                namespace=namespace or allowed_namespace,
                rationale=rationale,
                name=name,
                manifest=manifest,
                patch=patch,
                replicas=replicas,
                session_id=session_id,
            )
        except Exception as exc:  # noqa: BLE001 — surface validation errors to the LLM as text
            LOG.warning("[write] propose rejected: %s", exc)
            return f"PROPOSAL REJECTED (not recorded): {exc}"

        if proposal.status == ProposalStatus.DENIED:
            return f"PROPOSAL DENIED: {proposal.outcome} No change was or will be made."

        return (
            f"PROPOSAL {proposal.id} recorded and is PENDING human approval — "
            f"nothing has been changed.\n"
            f"Intent: {proposal.human_summary()}\n"
            f"Rationale: {proposal.rationale}\n"
            f"Server dry-run preview:\n{proposal.preview}\n\n"
            f"Tell the user exactly what will happen and ask them to Approve or "
            f"Reject proposal {proposal.id}. Do NOT say it is done."
        )

    return propose_write

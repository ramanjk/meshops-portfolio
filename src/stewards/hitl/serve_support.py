"""Shared FastAPI plumbing for the gated-write chat servers (ADR-0011).

Every steward's ``serve.py`` builds its own FastAPI app (per-steward isolation is
the house convention), but the write-path wiring — the request/response models,
the background poll loop that reconciles an async approval channel, the human
``/approve``,``/reject`` decision handler, and the browser-side proposal card —
is identical. Factoring it here keeps the three servers in lock-step and means a
fix to the HITL UX lands everywhere at once.

Read-only servers never import this module.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from .channels import ApprovalChannel
from .gate import WriteGate

LOG = logging.getLogger("meshops.hitl")

# The chat channel can approve in seconds; an async PR review may take hours or
# days, so the gate TTL must outlive human review. Bump it for the PR channel.
PR_CHANNEL_MIN_TTL_SECONDS = 7 * 24 * 3600


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatReply(BaseModel):
    reply: str
    session_id: str
    trace_id: str | None = None
    # When the steward proposes a write this turn, the pending proposal(s) are
    # surfaced here so the UI can render Approve/Reject controls (chat channel)
    # or a "Review PR" link (github_pr channel). Empty/None in the read-only path.
    pending: list[dict] | None = None


class DecisionRequest(BaseModel):
    proposal_id: str
    session_id: str | None = None


# Browser-side JS injected into each write-enabled chat page. It renders a
# proposal card with Approve/Reject buttons (chat channel) or a PR link (async
# channel), and posts human decisions back to /approve,/reject. Shared verbatim
# so all three stewards present an identical HITL affordance.
PROPOSAL_JS = """
  async function decide(url, id, card) {
    card.querySelectorAll('button').forEach(b => b.disabled = true);
    try {
      const r = await fetch(url, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({proposal_id: id, session_id: sessionId})
      });
      const j = await r.json();
      add('Gate', j.reply ?? JSON.stringify(j));
    } catch (err) { add('Gate', '(decision failed) ' + err); }
  }
  function addProposal(p) {
    const d = document.createElement('div');
    d.className = 'msg bot';
    d.innerHTML = '<div class="role">Proposal ' + p.id + ' — awaiting your approval</div>';
    const intent = document.createElement('div'); intent.textContent = p.summary;
    const pre = document.createElement('pre');
    pre.style.cssText = 'white-space:pre-wrap;font-size:.8rem;opacity:.85;margin:.4rem 0;';
    pre.textContent = p.preview || '(no preview)';
    d.appendChild(intent); d.appendChild(pre);
    if (p.external_ref) {
      const link = document.createElement('a');
      link.href = p.external_ref; link.target = '_blank'; link.rel = 'noopener';
      link.textContent = 'Review & merge PR to approve (close to reject) →';
      link.style.cssText = 'color:#2563eb;font-weight:600;';
      d.appendChild(link);
    } else {
      const row = document.createElement('div'); row.style.cssText = 'display:flex;gap:.5rem;';
      const ok = document.createElement('button'); ok.textContent = 'Approve';
      const no = document.createElement('button'); no.textContent = 'Reject';
      no.style.background = '#dc2626';
      ok.onclick = () => decide('/approve', p.id, d);
      no.onclick = () => decide('/reject', p.id, d);
      row.appendChild(ok); row.appendChild(no);
      d.appendChild(row);
    }
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  }
"""


async def poll_loop(  # pragma: no cover - timing loop
    channel: ApprovalChannel, gate: WriteGate, interval: int
) -> None:
    """Periodically reconcile external approval state (PR merges/closes)."""
    LOG.info("[chat] approval poll loop started (every %ss)", interval)
    while True:
        try:
            await asyncio.sleep(interval)
            changed = await asyncio.to_thread(channel.sync, gate)
            for p in changed:
                LOG.info("[chat] reconciled %s -> %s via %s", p.id, p.status.value, channel.name)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("[chat] approval poll iteration failed")


def pending_payload(gate: WriteGate, session_id: str) -> list[dict] | None:
    """Serialise a session's pending proposals for the ChatReply.pending field."""
    proposals = gate.pending_for_session(session_id)
    return [
        {
            "id": p.id,
            "summary": p.human_summary(),
            "preview": p.preview,
            "external_ref": p.external_ref,
        }
        for p in proposals
    ] or None


def decide(state: dict[str, Any], req: DecisionRequest, *, approve: bool) -> dict[str, str]:
    """Resolve a pending proposal at the HITL gate (the human's decision)."""
    gate: WriteGate | None = state.get("gate")
    if gate is None:
        return {"status": "error", "reply": "This steward is read-only; there is nothing to approve."}
    approver = "operator (chat)"
    try:
        proposal = gate.approve(req.proposal_id, approver) if approve else gate.reject(
            req.proposal_id, approver
        )
    except (KeyError, ValueError) as exc:
        return {"status": "error", "reply": str(exc)}

    if proposal.status.value == "executed":
        reply = f"✅ Approved and executed {proposal.id}: {proposal.human_summary()} → {proposal.outcome}"
    elif proposal.status.value == "rejected":
        reply = f"🚫 Rejected {proposal.id}: no change was made."
    elif proposal.status.value == "denied":
        reply = f"⛔ Denied for {proposal.id}: {proposal.outcome} (no change made)."
    else:
        reply = f"⚠️ {proposal.id} {proposal.status.value}: {proposal.outcome}"
    return {"status": proposal.status.value, "reply": reply, "proposal_id": proposal.id}

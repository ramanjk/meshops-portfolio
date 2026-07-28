"""Interactive chat server for the hello-inference steward.

Enabled with ``CHAT_ENABLED=true``. Serves a small HTTP API (and a minimal web
UI) so you can talk to the Inference Steward's persona and exercise its
read-only MCP tools (aks-mcp, prom-mcp). This is a long-lived process, so the
Deployment pod stays ``Running`` instead of completing/restarting.

Endpoints:
  GET  /            -> minimal HTML chat page
  GET  /healthz     -> liveness probe
  POST /chat        -> {"message": str, "session_id"?: str}
                       -> {"reply": str, "session_id": str, "trace_id": str}
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from contextlib import AsyncExitStack
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from opentelemetry.trace import SpanKind
from opentelemetry.trace.span import format_trace_id
from pydantic import BaseModel

from . import agent as agent_module
from .approval_channels import ApprovalChannel, build_channel
from .settings import Settings
from .write_gate import KubectlApplier, WriteGate
from .write_tool import build_propose_write_tool, current_session_id

LOG = logging.getLogger("meshops.hello-inference.chat")

# The chat channel can approve in seconds; an async PR review may take hours or
# days, so the gate TTL must outlive human review. Bump it for the PR channel.
_PR_CHANNEL_MIN_TTL_SECONDS = 7 * 24 * 3600


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


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Inference Steward — chat</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem; }
  h1 { font-size: 1.25rem; }
  #log { border: 1px solid #8884; border-radius: 8px; padding: 1rem; height: 60vh; overflow-y: auto; }
  .msg { margin: .5rem 0; padding: .5rem .75rem; border-radius: 8px; white-space: pre-wrap; }
  .user { background: #3b82f622; align-self: flex-end; }
  .bot  { background: #10b98122; }
  .role { font-size: .72rem; opacity: .6; margin-bottom: .15rem; }
  form { display: flex; gap: .5rem; margin-top: .75rem; }
  input { flex: 1; padding: .6rem; border-radius: 8px; border: 1px solid #8884; }
  button { padding: .6rem 1rem; border-radius: 8px; border: 0; background: #2563eb; color: #fff; cursor: pointer; }
  button:disabled { opacity: .5; cursor: default; }
</style>
</head>
<body>
  <h1>🛠️ Inference Steward — chat</h1>
  <div id="log"></div>
  <form id="f">
    <input id="m" autocomplete="off" placeholder="Ask about the KAITO workspace, replicas, GPU…" autofocus/>
    <button id="b" type="submit">Send</button>
  </form>
<script>
  const log = document.getElementById('log');
  const form = document.getElementById('f');
  const input = document.getElementById('m');
  const btn = document.getElementById('b');
  let sessionId = null;
  function add(role, text) {
    const d = document.createElement('div');
    d.className = 'msg ' + (role === 'You' ? 'user' : 'bot');
    d.innerHTML = '<div class="role">' + role + '</div>';
    d.appendChild(document.createTextNode(text));
    log.appendChild(d); log.scrollTop = log.scrollHeight;
  }
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
      // Async channel (github_pr): the decision happens by merging/closing the PR.
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
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const msg = input.value.trim(); if (!msg) return;
    add('You', msg); input.value = ''; btn.disabled = true;
    try {
      const r = await fetch('/chat', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message: msg, session_id: sessionId})
      });
      const j = await r.json();
      if (j.session_id) sessionId = j.session_id;
      add('Steward', j.reply ?? ('(error) ' + JSON.stringify(j)));
      if (Array.isArray(j.pending)) j.pending.forEach(addProposal);
    } catch (err) { add('Steward', '(request failed) ' + err); }
    finally { btn.disabled = false; input.focus(); }
  });
</script>
</body>
</html>
"""


def _friendly_error(exc: Exception) -> str | None:
    """Render a calm, on-persona message for known-benign LLM backend failures.

    Azure OpenAI's content-safety filter (and the agent framework's handling of
    it) surfaces as an opaque exception — e.g. ``'ContentFiltered' is not a valid
    ContentFilterCodes`` — rather than a clean refusal, which would otherwise leak
    a raw stack string to the chat user. We detect that (and transient rate
    limits) and reply gracefully. The unsafe or failed action never executed
    regardless: this steward is read-only. Returns None for unrecognised errors so
    the caller falls back to the generic message.
    """
    text = str(exc).lower()
    if "contentfilter" in text or "content_filter" in text or "responsible ai" in text:
        return (
            "I can't help with that request — it was flagged by the platform's "
            "content-safety filter, so I won't act on it. I'm a read-only steward "
            "regardless. Ask me about what I observe and I'll gladly help."
        )
    if "rate limit" in text or "too_many_requests" in text or "429" in text:
        return (
            "I'm being rate-limited by the language model right now — please retry "
            "in a few seconds."
        )
    return None


def _build_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Inference Steward Chat")
    state: dict[str, Any] = {}

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - integration path
        agent_module._start_prom_exporter(settings.otel_prometheus_port)
        agent_module._enable_langfuse_and_otel(settings)
        stack = AsyncExitStack()
        aks_tool, prom_tool = agent_module.build_mcp_tools(settings)
        await stack.enter_async_context(aks_tool)
        await stack.enter_async_context(prom_tool)
        chat = agent_module._build_chat_client(settings)

        tools: list[Any] = [aks_tool, prom_tool]
        # Iteration 2: gated write. Only when write is deliberately enabled do we
        # load the write-capable persona and hand the agent the single, NON-
        # mutating propose_write tool. Off = byte-for-byte the read-only steward.
        if settings.write_enabled:
            # An async approval channel (github_pr) may take hours/days, so the
            # gate must not expire the proposal before the human decides.
            ttl = settings.write_proposal_ttl_seconds
            if settings.write_approval_channel == "github_pr":
                ttl = max(ttl, _PR_CHANNEL_MIN_TTL_SECONDS)
            gate = WriteGate(
                KubectlApplier(kubectl_binary=settings.kubectl_binary),
                allowed_namespace=settings.write_namespace,
                ttl_seconds=ttl,
            )
            state["gate"] = gate
            channel = build_channel(settings, gate)
            state["channel"] = channel
            tools.append(build_propose_write_tool(gate, settings.write_namespace))
            persona = agent_module._read_prompt("inference-steward.gated-write.chat.md")
            LOG.info(
                "[chat] WRITE-ENABLED: HITL gate armed for ns/%s via '%s' channel",
                settings.write_namespace, channel.name,
            )
            # For an async channel, poll the external source (PR state) so merges
            # made outside the chat UI are reconciled into gate decisions.
            if channel.name == "github_pr":
                state["poll_task"] = asyncio.create_task(
                    _poll_loop(channel, gate, settings.github_poll_seconds)
                )
        else:
            state["gate"] = None
            state["channel"] = None
            persona = agent_module._read_prompt("inference-steward.chat.md")

        agent = chat.as_agent(
            name="hello-inference-chat",
            id="hello-inference-chat",
            instructions=persona,
            tools=tools,
        )
        state["stack"] = stack
        state["agent"] = agent
        state["sessions"] = {}
        LOG.info("[chat] ready; persona loaded, MCP tools connected")

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - integration path
        poll_task: asyncio.Task | None = state.get("poll_task")
        if poll_task is not None:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
        stack: AsyncExitStack | None = state.get("stack")
        if stack is not None:
            await stack.aclose()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> str:
        return _INDEX_HTML

    @app.post("/chat", response_model=ChatReply)
    async def chat_endpoint(req: ChatRequest) -> ChatReply:
        agent = state["agent"]
        sessions: dict[str, Any] = state["sessions"]
        session_id = req.session_id or uuid.uuid4().hex
        session = sessions.get(session_id)
        if session is None:
            session = agent.create_session(session_id=session_id)
            sessions[session_id] = session

        gate: WriteGate | None = state.get("gate")
        token = current_session_id.set(session_id)
        tracer = agent_module.get_tracer()
        trace_hex: str | None = None
        with tracer.start_as_current_span(
            "inference.steward.chat", kind=SpanKind.CLIENT
        ) as span:
            trace_hex = format_trace_id(span.get_span_context().trace_id)
            try:
                result = await agent.run(req.message, session=session)
                reply = result.text if hasattr(result, "text") else str(result)
            except Exception as exc:  # noqa: BLE001 - report errors to the caller
                LOG.exception("[chat] turn failed")
                span.record_exception(exc)
                reply = _friendly_error(exc) or f"Sorry — I hit an error handling that: {exc}"
            finally:
                current_session_id.reset(token)

        pending = None
        if gate is not None:
            channel: ApprovalChannel | None = state.get("channel")
            proposals = gate.pending_for_session(session_id)
            # For an async channel, publish any not-yet-published proposal (open a
            # PR) off the event loop. The gate stays pure; the channel does I/O.
            if channel is not None and channel.name != "chat":
                for p in proposals:
                    if p.external_ref is None:
                        await asyncio.to_thread(channel.open, p)
            pending = [
                {
                    "id": p.id,
                    "summary": p.human_summary(),
                    "preview": p.preview,
                    "external_ref": p.external_ref,
                }
                for p in proposals
            ] or None
        return ChatReply(
            reply=reply.strip(), session_id=session_id, trace_id=trace_hex, pending=pending
        )

    @app.post("/approve")
    async def approve_endpoint(req: DecisionRequest) -> dict[str, str]:
        return _decide(state, req, approve=True)

    @app.post("/reject")
    async def reject_endpoint(req: DecisionRequest) -> dict[str, str]:
        return _decide(state, req, approve=False)

    @app.post("/reconcile")
    async def reconcile_endpoint() -> dict[str, Any]:
        """Force an immediate poll of the async approval channel (PR states).

        The background loop already does this on an interval; this endpoint lets
        an operator (or a future webhook) trigger reconciliation on demand.
        """
        gate: WriteGate | None = state.get("gate")
        channel: ApprovalChannel | None = state.get("channel")
        if gate is None or channel is None or channel.name == "chat":
            return {"status": "noop", "resolved": []}
        changed = await asyncio.to_thread(channel.sync, gate)
        return {
            "status": "ok",
            "resolved": [
                {"id": p.id, "status": p.status.value, "outcome": p.outcome} for p in changed
            ],
        }

    return app


async def _poll_loop(
    channel: ApprovalChannel, gate: WriteGate, interval: int
) -> None:  # pragma: no cover - timing loop
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
        except Exception:  # noqa: BLE001 - a poll error must not kill the loop
            LOG.exception("[chat] approval poll iteration failed")


def _decide(state: dict[str, Any], req: DecisionRequest, *, approve: bool) -> dict[str, str]:
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
        reply = f"⛔ Denied by RBAC/scope for {proposal.id}: {proposal.outcome} (no change made)."
    else:
        reply = f"⚠️ {proposal.id} {proposal.status.value}: {proposal.outcome}"
    return {"status": proposal.status.value, "reply": reply, "proposal_id": proposal.id}


def serve(settings: Settings) -> None:
    """Blocking entry point: run the chat HTTP server."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = _build_app(settings)
    LOG.info("[chat] serving on 0.0.0.0:%s", settings.chat_port)
    uvicorn.run(app, host="0.0.0.0", port=settings.chat_port, log_level="info")

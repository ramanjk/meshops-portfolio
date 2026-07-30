"""Interactive chat server for the hello-sre steward.

Enabled with ``CHAT_ENABLED=true``. Serves a small HTTP API (and a minimal web
UI) so you can talk to the SRE Steward's persona and exercise its three
read-only correlation tools (aks-mcp, prom-mcp, langfuse-mcp). This is a
long-lived process, so the Deployment pod stays ``Running`` instead of
completing/restarting.

Read-only by default. When ``WRITE_ENABLED=true`` (Iteration 2) the steward also
gains the single, NON-mutating ``propose_scale`` tool and the gated-write
persona; every actuation still passes the HITL gate (ADR-0011) and the
namespaced writer RBAC Role. The write-path plumbing is shared across stewards
via :mod:`stewards.hitl`.

Endpoints:
  GET  /            -> minimal HTML chat page
  GET  /healthz     -> liveness probe
  POST /chat        -> {"message": str, "session_id"?: str}
                       -> {"reply": str, "session_id": str, "trace_id": str,
                           "pending": [proposal, …] | null}
  POST /approve     -> resolve a pending proposal (chat channel)
  POST /reject      -> reject a pending proposal (chat channel)
  POST /reconcile   -> force a poll of the async approval channel (github_pr)
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

from ..hitl import WriteGate, build_channel, current_session_id
from ..hitl.channels import ApprovalChannel
from ..hitl.serve_support import (
    PR_CHANNEL_MIN_TTL_SECONDS,
    PROPOSAL_JS,
    ChatReply,
    ChatRequest,
    DecisionRequest,
    decide,
    pending_payload,
    poll_loop,
)
from . import agent as agent_module
from .settings import Settings
from .write import KubectlScaleApplier, build_propose_scale_tool

LOG = logging.getLogger("meshops.hello-sre.chat")


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>SRE Steward — chat</title>
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
  <h1>🛠️ SRE Steward — chat</h1>
  <div id="log"></div>
  <form id="f">
    <input id="m" autocomplete="off" placeholder="Ask about incidents, metrics, GPU, health…" autofocus/>
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
__PROPOSAL_JS__
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
""".replace("__PROPOSAL_JS__", PROPOSAL_JS)


def _friendly_error(exc: Exception) -> str | None:
    """Render a calm, on-persona message for known-benign LLM backend failures.

    Azure OpenAI's content-safety filter (and the agent framework's handling of
    it) surfaces as an opaque exception rather than a clean refusal, which would
    otherwise leak a raw stack string to the chat user. We detect that (and
    transient rate limits) and reply gracefully. The unsafe or failed action
    never executed regardless: any write is HITL-gated. Returns None for
    unrecognised errors so the caller falls back to the generic message.
    """
    text = str(exc).lower()
    if "contentfilter" in text or "content_filter" in text or "responsible ai" in text:
        return (
            "I can't help with that request — it was flagged by the platform's "
            "content-safety filter, so I won't act on it. Any change I make is "
            "human-gated regardless. Ask me about what I observe and I'll gladly help."
        )
    if "rate limit" in text or "too_many_requests" in text or "429" in text:
        return (
            "I'm being rate-limited by the language model right now — please retry "
            "in a few seconds."
        )
    return None


def _build_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="SRE Steward Chat")
    state: dict[str, Any] = {}

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - integration path
        agent_module._start_prom_exporter(settings.otel_prometheus_port)
        agent_module._enable_langfuse_and_otel(settings)
        stack = AsyncExitStack()
        aks_tool, prom_tool, langfuse_tool = agent_module.build_mcp_tools(settings)
        await stack.enter_async_context(aks_tool)
        await stack.enter_async_context(prom_tool)
        await stack.enter_async_context(langfuse_tool)
        chat = agent_module._build_chat_client(settings)

        tools: list[Any] = [aks_tool, prom_tool, langfuse_tool]
        # Iteration 2: gated write. Only when write is deliberately enabled do we
        # load the write-capable persona and hand the agent the single, NON-
        # mutating propose_scale tool. Off = byte-for-byte the read-only steward.
        if settings.write_enabled:
            ttl = settings.write_proposal_ttl_seconds
            if settings.write_approval_channel == "github_pr":
                ttl = max(ttl, PR_CHANNEL_MIN_TTL_SECONDS)
            gate = WriteGate(
                KubectlScaleApplier(settings.kubectl_binary),
                ttl_seconds=ttl,
            )
            state["gate"] = gate
            channel = build_channel(settings, gate)
            state["channel"] = channel
            tools.append(
                build_propose_scale_tool(
                    gate,
                    allowed_namespace=settings.scale_namespace,
                    allowed_deployments=settings.allowed_deployment_set(),
                    min_replicas=settings.scale_min_replicas,
                    max_replicas=settings.scale_max_replicas,
                )
            )
            persona = agent_module._read_prompt("sre-steward.gated-write.chat.md")
            LOG.info(
                "[chat] WRITE-ENABLED: HITL gate armed for Deployment scale in "
                "ns/%s via '%s' channel",
                settings.scale_namespace,
                channel.name,
            )
            if channel.name == "github_pr":
                state["poll_task"] = asyncio.create_task(
                    poll_loop(channel, gate, settings.github_poll_seconds)
                )
        else:
            state["gate"] = None
            state["channel"] = None
            persona = agent_module._read_prompt("sre-steward.chat.md")

        agent = chat.as_agent(
            name="hello-sre-chat",
            id="hello-sre-chat",
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
            "sre.steward.chat", kind=SpanKind.CLIENT
        ) as span:
            trace_hex = format_trace_id(span.get_span_context().trace_id)
            try:
                result = await agent.run(req.message, session=session)
                reply = result.text if hasattr(result, "text") else str(result)
            except Exception as exc:
                LOG.exception("[chat] turn failed")
                span.record_exception(exc)
                reply = _friendly_error(exc) or f"Sorry — I hit an error handling that: {exc}"
            finally:
                current_session_id.reset(token)

        pending = None
        if gate is not None:
            channel: ApprovalChannel | None = state.get("channel")
            if channel is not None and channel.name != "chat":
                for p in gate.pending_for_session(session_id):
                    if p.external_ref is None:
                        await asyncio.to_thread(channel.open, p)
            pending = pending_payload(gate, session_id)
        return ChatReply(
            reply=reply.strip(), session_id=session_id, trace_id=trace_hex, pending=pending
        )

    @app.post("/approve")
    async def approve_endpoint(req: DecisionRequest) -> dict[str, str]:
        return decide(state, req, approve=True)

    @app.post("/reject")
    async def reject_endpoint(req: DecisionRequest) -> dict[str, str]:
        return decide(state, req, approve=False)

    @app.post("/reconcile")
    async def reconcile_endpoint() -> dict[str, Any]:
        """Force an immediate poll of the async approval channel (PR states)."""
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


def serve(settings: Settings) -> None:
    """Blocking entry point: run the chat HTTP server."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = _build_app(settings)
    LOG.info("[chat] serving on 0.0.0.0:%s", settings.chat_port)
    uvicorn.run(app, host="0.0.0.0", port=settings.chat_port, log_level="info")

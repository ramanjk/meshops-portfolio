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
from .settings import Settings

LOG = logging.getLogger("meshops.hello-inference.chat")


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatReply(BaseModel):
    reply: str
    session_id: str
    trace_id: str | None = None


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
  <h1>🛠️ Inference Steward — chat <small>(read-only)</small></h1>
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
    } catch (err) { add('Steward', '(request failed) ' + err); }
    finally { btn.disabled = false; input.focus(); }
  });
</script>
</body>
</html>
"""


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
        system_prompt = agent_module._read_prompt("inference-steward.chat.md")
        agent = chat.as_agent(
            name="hello-inference-chat",
            id="hello-inference-chat",
            instructions=system_prompt,
            tools=[aks_tool, prom_tool],
        )
        state["stack"] = stack
        state["agent"] = agent
        state["sessions"] = {}
        LOG.info("[chat] ready; persona loaded, MCP tools connected")

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover - integration path
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
                reply = f"Sorry — I hit an error handling that: {exc}"
        return ChatReply(reply=reply.strip(), session_id=session_id, trace_id=trace_hex)

    return app


def serve(settings: Settings) -> None:
    """Blocking entry point: run the chat HTTP server."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    app = _build_app(settings)
    LOG.info("[chat] serving on 0.0.0.0:%s", settings.chat_port)
    uvicorn.run(app, host="0.0.0.0", port=settings.chat_port, log_level="info")

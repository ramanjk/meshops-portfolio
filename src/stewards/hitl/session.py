"""Per-request session propagation for the gated-write path.

The LLM's non-mutating propose tool needs to stamp each proposal with the chat
session that produced it (so the UI can surface *that user's* pending proposals)
without threading a session_id through the agent framework's tool-call plumbing.
A ContextVar set by the chat endpoint immediately before ``agent.run`` — and
reset in a ``finally`` — is the clean, framework-agnostic way to do that.

This is intentionally trivial and dependency-free so every steward's write tool
can import it without pulling in agent/LLM code.
"""
from __future__ import annotations

from contextvars import ContextVar

# Set by the chat endpoint before invoking the agent; read by the propose tool.
current_session_id: ContextVar[str | None] = ContextVar("current_session_id", default=None)

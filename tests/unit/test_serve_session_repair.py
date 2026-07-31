"""Unit tests for the chat servers' _repair_session helper (all six stewards).

When ``agent.run`` is interrupted mid tool-loop (e.g. a transient 429 after a
function call was issued but before its result was recorded), the session history
is left with a ``function_call`` content part that has no matching
``function_result``. Replaying that on the next turn makes the OpenAI Responses
API reject the request with ``400 - No tool output found for function call``.
``_repair_session`` prunes the unmatched parts so the retry replays valid
history. The helper is duplicated verbatim across the isolated steward modules,
so we assert every copy behaves identically.
"""
from __future__ import annotations

import importlib
from typing import Any

import pytest
from agent_framework import Content, Message

SERVE_MODULES = [
    "stewards.inference.serve",
    "stewards.pipeline.serve",
    "stewards.quality.serve",
    "stewards.sre.serve",
    "stewards.gateway.serve",
    "stewards.security.serve",
]


class _FakeSession:
    """Minimal stand-in for AgentSession: only .state and .session_id are read."""

    def __init__(self, messages: list[Message]) -> None:
        self.session_id = "sess-test"
        self.state: dict[str, Any] = {"messages": messages}


@pytest.fixture(params=SERVE_MODULES)
def repair(request: pytest.FixtureRequest):
    mod = importlib.import_module(request.param)
    return mod._repair_session


def _call_ids(session: _FakeSession) -> set[str]:
    ids: set[str] = set()
    for msg in session.state["messages"]:
        for part in msg.contents:
            if getattr(part, "call_id", None):
                ids.add(part.call_id)
    return ids


def test_drops_unmatched_function_call(repair) -> None:
    session = _FakeSession(
        [
            Message(role="user", contents=[Content.from_text("check health")]),
            # assistant emitted a tool call but the run crashed before the result
            Message(
                role="assistant",
                contents=[Content.from_function_call(call_id="call_x", name="read", arguments={})],
            ),
        ]
    )
    repair(session)
    # The dangling function_call is gone (its now-empty message dropped too).
    assert "call_x" not in _call_ids(session)
    remaining = session.state["messages"]
    assert all(
        getattr(p, "type", None) != "function_call" for m in remaining for p in m.contents
    )
    # The valid user turn survives.
    assert any(
        getattr(p, "type", None) == "text" for m in remaining for p in m.contents
    )


def test_keeps_matched_pairs(repair) -> None:
    session = _FakeSession(
        [
            Message(role="user", contents=[Content.from_text("check health")]),
            Message(
                role="assistant",
                contents=[Content.from_function_call(call_id="c1", name="read", arguments={})],
            ),
            Message(
                role="tool",
                contents=[Content.from_function_result(call_id="c1", result="ok")],
            ),
        ]
    )
    before = len(session.state["messages"])
    repair(session)
    # Nothing pruned: the call has its matching result.
    assert len(session.state["messages"]) == before
    assert "c1" in _call_ids(session)


def test_preserves_text_alongside_unmatched_call(repair) -> None:
    session = _FakeSession(
        [
            Message(
                role="assistant",
                contents=[
                    Content.from_text("I'll read the cluster."),
                    Content.from_function_call(call_id="c2", name="read", arguments={}),
                ],
            ),
        ]
    )
    repair(session)
    remaining = session.state["messages"]
    # Message survives (had text), but the unmatched call part is removed.
    assert len(remaining) == 1
    types = [getattr(p, "type", None) for p in remaining[0].contents]
    assert "text" in types
    assert "function_call" not in types


def test_drops_unmatched_function_result(repair) -> None:
    session = _FakeSession(
        [
            Message(
                role="tool",
                contents=[Content.from_function_result(call_id="orphan", result="ok")],
            ),
        ]
    )
    repair(session)
    assert "orphan" not in _call_ids(session)


def test_noop_on_clean_or_empty_session(repair) -> None:
    empty = _FakeSession([])
    repair(empty)
    assert empty.state["messages"] == []

    clean = _FakeSession([Message(role="user", contents=[Content.from_text("hi")])])
    repair(clean)
    assert len(clean.state["messages"]) == 1

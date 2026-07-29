"""Unit tests for the chat servers' _friendly_error helper (all three stewards).

The helper turns opaque Azure OpenAI content-filter / rate-limit exceptions into
calm, on-persona messages instead of leaking a raw stack string to the chat user.
It is duplicated verbatim across the isolated steward modules, so we assert every
copy behaves identically.
"""
from __future__ import annotations

import importlib

import pytest

SERVE_MODULES = [
    "stewards.inference.serve",
    "stewards.pipeline.serve",
    "stewards.quality.serve",
]


@pytest.fixture(params=SERVE_MODULES)
def friendly_error(request: pytest.FixtureRequest):
    mod = importlib.import_module(request.param)
    return mod._friendly_error


def test_content_filter_variants_detected(friendly_error) -> None:
    for msg in (
        "'ContentFiltered' is not a valid ContentFilterCodes",
        "Error code: 400 - the response was filtered due to content_filter policy",
        "ResponsibleAIPolicyViolation: flagged by Responsible AI",
    ):
        reply = friendly_error(Exception(msg))
        assert reply is not None
        assert "content-safety filter" in reply
        assert "won't act on it" in reply


def test_rate_limit_detected(friendly_error) -> None:
    reply = friendly_error(Exception("Error code: 429 - too_many_requests: rate limit exceeded"))
    assert reply is not None
    assert "rate-limited" in reply


def test_unknown_error_falls_through(friendly_error) -> None:
    assert friendly_error(Exception("some unrelated KeyError in tool call")) is None

"""Tiny Langfuse-MCP server — read-only access to a Langfuse project.

This is intentionally minimal — it is NOT a general-purpose Langfuse MCP. In
iteration-03 it exists so the Quality steward has a stable, read-only tool
interface to observe LLM traces and evaluation scores (the raw material for
quality/drift reasoning) without any ability to create, update, or delete.

The underlying endpoint is the Langfuse public REST API. Authentication is
HTTP Basic: the project's public key is the username and the secret key is the
password (the same LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY the steward already
holds from Key Vault).

Reference docs:
  https://api.reference.langfuse.com/
  https://langfuse.com/docs/api
  https://modelcontextprotocol.io/specification
"""
from __future__ import annotations

import os
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("langfuse-mcp")


def _base_url() -> str:
    """Langfuse public API base, derived from the Langfuse host URL."""
    root = os.environ.get("LANGFUSE_HOST", "http://langfuse-web.langfuse.svc.cluster.local:3000")
    return root.rstrip("/") + "/api/public"


def _auth() -> httpx.BasicAuth:
    """HTTP Basic auth: public key = username, secret key = password."""
    return httpx.BasicAuth(
        os.environ.get("LANGFUSE_PUBLIC_KEY", ""),
        os.environ.get("LANGFUSE_SECRET_KEY", ""),
    )


async def _get(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=15.0, auth=_auth()) as client:
        resp = await client.get(f"{_base_url()}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def list_traces(
    limit: Annotated[int, Field(description="Max traces to return (most recent first).", ge=1, le=100)] = 50,
    page: Annotated[int, Field(description="1-based page number.", ge=1, le=1000)] = 1,
) -> dict[str, object]:
    """List recent traces in the Langfuse project (read-only).

    Returns the raw Langfuse ``GET /api/public/traces`` response body, whose
    ``data`` array carries each trace's ``id``, ``name``, ``timestamp``,
    ``userId``, ``sessionId`` and any attached top-level ``scores``. ``meta``
    carries pagination totals.
    """
    return await _get("/traces", {"limit": limit, "page": page})


@mcp.tool()
async def get_trace(
    trace_id: Annotated[str, Field(description="Trace id to fetch, from list_traces.")],
) -> dict[str, object]:
    """Get one trace's full detail (read-only), including its observations and
    any evaluation scores attached to it."""
    return await _get(f"/traces/{trace_id}")


@mcp.tool()
async def list_scores(
    limit: Annotated[int, Field(description="Max scores to return (most recent first).", ge=1, le=100)] = 50,
    page: Annotated[int, Field(description="1-based page number.", ge=1, le=1000)] = 1,
    name: Annotated[
        str | None,
        Field(description="Optional score name to filter by, e.g. 'faithfulness'."),
    ] = None,
) -> dict[str, object]:
    """List evaluation scores in the Langfuse project (read-only).

    Returns the raw Langfuse ``GET /api/public/scores`` response body; each
    score in ``data`` carries ``name``, ``value``, ``dataType``
    (NUMERIC/CATEGORICAL/BOOLEAN), ``traceId`` and ``timestamp`` — the signal the
    Quality steward reasons over for eval health and drift.
    """
    params: dict[str, object] = {"limit": limit, "page": page}
    if name:
        params["name"] = name
    return await _get("/scores", params)


def run() -> None:
    mcp.run(transport="stdio")

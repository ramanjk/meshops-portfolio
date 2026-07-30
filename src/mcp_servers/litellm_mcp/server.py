"""Tiny LiteLLM-MCP server — read-only view of a LiteLLM proxy's Gateway plane.

This is intentionally minimal — it is NOT a general-purpose LiteLLM admin MCP.
In this read-only iteration it exists so the Gateway Steward has a stable tool
interface for the three things it needs to reason about the routing plane:

  * ``list_routes``  — the configured model routes and their per-route budget caps
                       (``model_info.max_budget``) — the governance surface.
  * ``route_health`` — per-deployment health as LiteLLM sees the upstreams.

Live per-request spend is deliberately NOT exposed here: LiteLLM's ``/spend``
endpoints require a connected database, which the lab proxy does not run. The
budget *cap* (the policy the steward governs) lives in the proxy config and is
fully readable without a DB.

Auth: the LiteLLM master key (``LITELLM_MASTER_KEY``) against ``LITELLM_BASE_URL``.
Every tool here issues only GETs — it can read the plane, never mutate it.

Reference docs:
  https://docs.litellm.ai/docs/proxy/model_management
  https://modelcontextprotocol.io/specification
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("litellm-mcp")


def _base() -> str:
    return os.environ["LITELLM_BASE_URL"].rstrip("/")


def _headers() -> dict[str, str]:
    key = os.environ.get("LITELLM_MASTER_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


@mcp.tool()
async def list_routes() -> dict[str, object]:
    """List the LiteLLM model routes and their per-route budget caps.

    Returns one entry per configured route with its logical name, the upstream
    model it maps to, and the ``max_budget`` cap declared in the proxy config.
    This is the routing + budget governance surface the Gateway Steward reasons
    about (and, in Iteration 2, proposes budget changes to).
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base()}/model/info", headers=_headers())
        resp.raise_for_status()
        data = resp.json().get("data", [])
    routes: list[dict[str, object]] = []
    for m in data:
        info = m.get("model_info", {}) or {}
        params = m.get("litellm_params", {}) or {}
        routes.append(
            {
                "route": m.get("model_name"),
                "upstream_model": params.get("model"),
                "api_base": params.get("api_base"),
                "api_version": params.get("api_version"),
                "max_budget": info.get("max_budget"),
            }
        )
    return {"route_count": len(routes), "routes": routes}


@mcp.tool()
async def route_health() -> dict[str, object]:
    """Report LiteLLM's health view of each route's upstream deployment.

    Returns healthy/unhealthy counts and, for any unhealthy upstream, the error
    LiteLLM last saw. Lets the steward correlate a route's budget/config against
    whether its upstream is actually serving.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{_base()}/health", headers=_headers())
        resp.raise_for_status()
        body = resp.json()
    healthy = [
        {"model": e.get("model"), "api_base": e.get("api_base")}
        for e in body.get("healthy_endpoints", [])
    ]
    unhealthy = [
        {"model": e.get("model"), "api_base": e.get("api_base"), "error": e.get("error")}
        for e in body.get("unhealthy_endpoints", [])
    ]
    return {
        "healthy_count": body.get("healthy_count", len(healthy)),
        "unhealthy_count": body.get("unhealthy_count", len(unhealthy)),
        "healthy_endpoints": healthy,
        "unhealthy_endpoints": unhealthy,
    }


def run() -> None:
    mcp.run(transport="stdio")

"""Tiny Prom-MCP server — exposes `query_promql` against Azure Managed Prometheus.

This is intentionally minimal — it is NOT a general-purpose Prometheus MCP.
In iteration-01 it exists so the agent has a stable tool interface for any
PromQL query; the underlying endpoint is Azure Monitor's Managed Prometheus
query API.

Reference docs:
  https://learn.microsoft.com/en-us/azure/azure-monitor/containers/prometheus-api-promql
  https://modelcontextprotocol.io/specification
"""
from __future__ import annotations

import os
from typing import Annotated

import httpx
from azure.identity.aio import DefaultAzureCredential
from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("prom-mcp")


async def _bearer_token() -> str:
    """Get an AAD bearer token for the Managed Prometheus query API."""
    cred = DefaultAzureCredential()
    token = await cred.get_token("https://prometheus.monitor.azure.com/.default")
    return token.token


@mcp.tool()
async def query_promql(
    query: Annotated[str, Field(description="PromQL expression, e.g. 'up == 1'.")],
    time: Annotated[str | None, Field(description="RFC3339 timestamp; None = now.")] = None,
) -> dict[str, object]:
    """Run an instant PromQL query against Azure Managed Prometheus.

    Returns the raw Prometheus query response body as a dict.
    """
    base = os.environ["AZURE_MONITOR_WORKSPACE_QUERY_URL"].rstrip("/")
    token = await _bearer_token()
    params: dict[str, str] = {"query": query}
    if time is not None:
        params["time"] = time
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{base}/api/v1/query",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()


def run() -> None:
    mcp.run(transport="stdio")

"""Tiny MLflow-MCP server — read-only access to an MLflow Model Registry.

This is intentionally minimal — it is NOT a general-purpose MLflow MCP. In
iteration-02 it exists so the Pipeline steward has a stable, read-only tool
interface to observe the model registry (registered models, versions, stage
tags) without any ability to register, transition, or delete.

The underlying endpoint is the MLflow REST API (2.0) served by the in-cluster
MLflow tracking server. No auth in the lab (in-cluster ClusterIP).

Reference docs:
  https://mlflow.org/docs/latest/rest-api.html
  https://modelcontextprotocol.io/specification
"""
from __future__ import annotations

import os
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import Field

mcp = FastMCP("mlflow-mcp")


def _base_url() -> str:
    """MLflow REST API base, derived from the tracking server URI."""
    root = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow.mlflow.svc.cluster.local:5000")
    return root.rstrip("/") + "/api/2.0/mlflow"


async def _get(path: str, params: dict[str, object] | None = None) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base_url()}{path}", params=params or {})
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def list_registered_models(
    max_results: Annotated[int, Field(description="Max registered models to return.", ge=1, le=1000)] = 100,
) -> dict[str, object]:
    """List registered models in the MLflow Model Registry (read-only).

    Returns the raw MLflow ``registered-models/search`` response body, whose
    ``registered_models`` array carries each model's name, tags, and
    ``latest_versions`` (with their ``current_stage``).
    """
    return await _get("/registered-models/search", {"max_results": max_results})


@mcp.tool()
async def get_registered_model(
    name: Annotated[str, Field(description="Registered model name, e.g. 'phi-4-mini-meshops'.")],
) -> dict[str, object]:
    """Get one registered model's detail (read-only), including latest versions
    per stage and tags."""
    return await _get("/registered-models/get", {"name": name})


@mcp.tool()
async def list_model_versions(
    name: Annotated[str, Field(description="Registered model name to list versions for.")],
    max_results: Annotated[int, Field(description="Max versions to return.", ge=1, le=1000)] = 200,
) -> dict[str, object]:
    """Search model versions for a registered model (read-only).

    Returns the raw MLflow ``model-versions/search`` response body; each version
    carries ``version``, ``current_stage`` (None/Staging/Production/Archived),
    ``status``, ``run_id``, and ``creation_timestamp``.
    """
    return await _get(
        "/model-versions/search",
        {"filter": f"name='{name}'", "max_results": max_results},
    )


def run() -> None:
    mcp.run(transport="stdio")

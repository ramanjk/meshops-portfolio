"""Tiny GitHub-Security-MCP — read-only view of the HITL *proposal queue*.

The Security Steward's substrate is not an infra plane — it is the stream of
**inputs the platform is about to trust**: the peer stewards' Human-in-the-Loop
(HITL) proposals, which arrive as GitHub pull requests (branch prefix ``hitl/``),
plus any other open PR to the repo (a runbook/RAG-corpus change). This shim gives
the steward a stable, *read-only* interface over that queue so it can classify
each pending input against an injection / confused-deputy / poisoning rubric:

  * ``list_open_proposals`` — the open PRs (number, title, author, branch, labels,
    whether it looks like a steward HITL proposal) — the vetting worklist.
  * ``get_proposal`` — one PR's full body + changed-file diffs — the actual text
    to classify (where a prompt-injection / confused-deputy payload would hide).

Every tool issues only GETs against the GitHub REST API — it can read the queue,
never mutate it. The gated *quarantine* write (add a label) lives in the steward's
write path (Iteration 2), never here.

Auth: a GitHub token (``GITHUB_TOKEN``) with read access to ``GITHUB_REPO``
(``owner/repo``). Reference: https://docs.github.com/en/rest/pulls
"""
from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-sec-mcp")

_API = "https://api.github.com"


def _repo() -> str:
    return os.environ["GITHUB_REPO"].strip("/")


def _headers() -> dict[str, str]:
    token = os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
    h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _proposal_prefix() -> str:
    return os.environ.get("PROPOSAL_BRANCH_PREFIX", "hitl/")


@mcp.tool()
async def list_open_proposals() -> dict[str, object]:
    """List the open pull requests awaiting review — the vetting worklist.

    Returns one entry per open PR with its number, title, author, head branch,
    current labels, and an ``is_steward_proposal`` flag (true when the branch
    starts with the configured HITL prefix, e.g. ``hitl/``). These are the
    inputs the Security Steward classifies; a steward proposal is a peer
    steward's gated write awaiting human approval, so vetting it is the
    confused-deputy / cross-steward catch surface.
    """
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{_API}/repos/{_repo()}/pulls",
            headers=_headers(),
            params={"state": "open", "per_page": 50},
        )
        resp.raise_for_status()
        prs = resp.json()
    prefix = _proposal_prefix()
    items: list[dict[str, object]] = []
    for pr in prs:
        head_ref = (pr.get("head") or {}).get("ref", "")
        items.append(
            {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "author": (pr.get("user") or {}).get("login"),
                "branch": head_ref,
                "labels": [lbl.get("name") for lbl in pr.get("labels", [])],
                "is_steward_proposal": head_ref.startswith(prefix),
                "created_at": pr.get("created_at"),
            }
        )
    return {"open_count": len(items), "proposals": items}


@mcp.tool()
async def get_proposal(pr_number: int) -> dict[str, object]:
    """Fetch one PR's body and changed-file diffs — the text to classify.

    Returns the PR title, author, branch, current labels, description body, and
    the per-file unified diffs (patches). This is the content the steward scans
    for a prompt-injection / confused-deputy / data-poisoning payload before it
    is trusted or merged.

    Args:
        pr_number: the open PR number to inspect (from ``list_open_proposals``).
    """
    async with httpx.AsyncClient(timeout=25.0) as client:
        pr_resp = await client.get(
            f"{_API}/repos/{_repo()}/pulls/{pr_number}", headers=_headers()
        )
        pr_resp.raise_for_status()
        pr = pr_resp.json()
        files_resp = await client.get(
            f"{_API}/repos/{_repo()}/pulls/{pr_number}/files",
            headers=_headers(),
            params={"per_page": 50},
        )
        files_resp.raise_for_status()
        files = files_resp.json()
    changed = [
        {
            "filename": f.get("filename"),
            "status": f.get("status"),
            "additions": f.get("additions"),
            "deletions": f.get("deletions"),
            "patch": (f.get("patch") or "")[:4000],
        }
        for f in files
    ]
    head_ref = (pr.get("head") or {}).get("ref", "")
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "author": (pr.get("user") or {}).get("login"),
        "branch": head_ref,
        "is_steward_proposal": head_ref.startswith(_proposal_prefix()),
        "state": pr.get("state"),
        "labels": [lbl.get("name") for lbl in pr.get("labels", [])],
        "body": (pr.get("body") or "")[:6000],
        "changed_files": changed,
    }


def run() -> None:
    mcp.run(transport="stdio")

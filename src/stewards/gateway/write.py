"""Iteration-2 gated write for the Gateway steward: change a route's budget cap.

The Gateway steward reads the LiteLLM routing plane (routes + per-route budgets +
upstream health). Its *one* mutation is **changing a route's per-route budget
cap** (``model_info.max_budget`` in the LiteLLM config) — the "per-route budget
cap" governance action from the agent catalog. When it concludes (and a human
agrees) that a route is over- or under-budgeted, it proposes a new cap; a human
approves; deterministic code patches the LiteLLM config ConfigMap and rolls the
proxy so it reloads — under a namespaced writer Role.

This module supplies the two domain pieces the shared HITL spine
(:mod:`stewards.hitl`) needs:

  * :class:`BudgetProposal` — the intent (route name, new budget cap).
  * :class:`LiteLLMBudgetApplier` — deterministic preview/apply that reads and
    patches the LiteLLM config ConfigMap via ``kubectl`` under the pod's bounded
    ServiceAccount token, then rolls the proxy Deployment.

Three layers cap blast radius (defence-in-depth):
  1. persona — the read-only persona has no propose tool at all;
  2. domain guard — :func:`build_propose_budget_tool` rejects any route outside
     the allowlist / budget outside the bounds *before* the gate stores it
     (recorded via :meth:`WriteGate.deny`, never approvable);
  3. RBAC — the writer Role is namespaced to ``budget_namespace`` and grants only
     ``configmaps`` get/patch + ``deployments`` get/patch (to roll the proxy); an
     approved-but-wrong request is still capped to that one config surface.

The LLM only ever calls :func:`build_propose_budget_tool`, which records a
proposal and returns ``PENDING``. It has no path to actuation (ADR-0011).
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from collections.abc import Callable

import yaml
from pydantic import Field

from ..hitl import ApplyError, Proposal, ProposalStatus, WriteGate, current_session_id

LOG = logging.getLogger("meshops.hello-gateway.write")


class BudgetProposal(Proposal):
    """A proposed per-route budget-cap change for one LiteLLM route."""

    route: str = Field(..., min_length=1, max_length=253)
    budget: float = Field(..., ge=0.0, le=1_000_000.0)

    def human_summary(self) -> str:
        return f"set budget cap of route '{self.route}' to ${self.budget:.2f}"

    def spec_dict(self) -> dict:
        return {
            "kind": "LiteLLMRouteBudget",
            "route": self.route,
            "max_budget": self.budget,
        }

    def audit_kind(self) -> str:
        return "route-budget"


def _as_budget(proposal: Proposal) -> BudgetProposal:
    if not isinstance(proposal, BudgetProposal):
        raise ApplyError(f"expected a BudgetProposal, got {type(proposal).__name__}")
    return proposal


class LiteLLMBudgetApplier:
    """Deterministic executor: patch the LiteLLM config ConfigMap + roll the proxy.

    LiteLLM's per-route budget cap lives in ``model_info.max_budget`` inside the
    proxy's ``config.yaml``, which is mounted from a ConfigMap. Changing it is a
    config edit (there is no live budget-write API without a proxy database), so
    the applier reads the ConfigMap, rewrites the one field with PyYAML, patches
    the ConfigMap, and rolls the Deployment so the proxy reloads. All actuation
    is deterministic code (never the LLM) under a bounded namespaced Role.
    """

    def __init__(
        self,
        *,
        namespace: str,
        configmap: str,
        config_key: str,
        deployment: str,
        kubectl_binary: str = "kubectl",
        timeout_seconds: int = 30,
    ) -> None:
        self._ns = namespace
        self._configmap = configmap
        self._config_key = config_key
        self._deployment = deployment
        self._kubectl = kubectl_binary
        self._timeout = timeout_seconds

    def _run(self, argv: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(  # noqa: S603 - argv built from validated config/proposal
                argv, capture_output=True, text=True, timeout=self._timeout, input=stdin
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover - env dependent
            raise ApplyError(f"kubectl timed out after {self._timeout}s") from exc
        except FileNotFoundError as exc:
            raise ApplyError(f"kubectl binary not found: {self._kubectl}") from exc

    def _read_config(self) -> dict:
        """Read + parse the LiteLLM config.yaml out of the ConfigMap."""
        jsonpath = "{.data." + self._config_key.replace(".", "\\.") + "}"
        proc = self._run([
            self._kubectl, "get", "configmap", self._configmap,
            "-n", self._ns, "-o", f"jsonpath={jsonpath}",
        ])
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            denied = "forbidden" in err.lower() or "cannot " in err.lower()
            raise ApplyError(err or f"kubectl exited {proc.returncode}", denied=denied)
        raw = proc.stdout or ""
        if not raw.strip():
            raise ApplyError(
                f"ConfigMap {self._configmap} has no '{self._config_key}' key or it is empty"
            )
        return yaml.safe_load(raw) or {}

    @staticmethod
    def _find_route(config: dict, route: str) -> dict | None:
        for entry in config.get("model_list", []) or []:
            if entry.get("model_name") == route:
                return entry
        return None

    def _current_budget(self, proposal: BudgetProposal) -> float | None:
        entry = self._find_route(self._read_config(), proposal.route)
        if entry is None:
            return None
        return (entry.get("model_info") or {}).get("max_budget")

    def preview(self, proposal: Proposal) -> str:
        """Dry-run: read the route's current budget cap and describe the delta.

        LiteLLM has no server-side dry-run for a config change, so we read the
        live ConfigMap value deterministically and report the intended
        transition. Reading also surfaces "route not found" / RBAC-forbidden
        errors before approval.
        """
        proposal = _as_budget(proposal)
        config = self._read_config()
        entry = self._find_route(config, proposal.route)
        if entry is None:
            known = ", ".join(
                e.get("model_name", "?") for e in (config.get("model_list") or [])
            )
            raise ApplyError(
                f"route '{proposal.route}' not found in LiteLLM config (known: {known})"
            )
        current = (entry.get("model_info") or {}).get("max_budget", "unset")
        return (
            f"LiteLLM route '{proposal.route}': budget cap {current} -> "
            f"${proposal.budget:.2f}. No change made (dry-run)."
        )

    def apply(self, proposal: Proposal) -> str:
        proposal = _as_budget(proposal)
        config = self._read_config()
        entry = self._find_route(config, proposal.route)
        if entry is None:
            raise ApplyError(f"route '{proposal.route}' not found in LiteLLM config")
        info = entry.setdefault("model_info", {})
        before = info.get("max_budget", "unset")
        info["max_budget"] = proposal.budget

        new_yaml = yaml.safe_dump(config, sort_keys=False)
        patch = json.dumps({"data": {self._config_key: new_yaml}})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=True) as fh:
            fh.write(patch)
            fh.flush()
            proc = self._run([
                self._kubectl, "patch", "configmap", self._configmap,
                "-n", self._ns, "--type", "merge", "--patch-file", fh.name,
            ])
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()
            denied = "forbidden" in err.lower() or "cannot " in err.lower()
            raise ApplyError(err or f"kubectl patch exited {proc.returncode}", denied=denied)

        roll = self._run([
            self._kubectl, "rollout", "restart", f"deployment/{self._deployment}", "-n", self._ns,
        ])
        if roll.returncode != 0:
            err = (roll.stderr or roll.stdout or "").strip()
            # The budget IS changed at this point; the roll is best-effort reload.
            LOG.warning("[write] budget patched but rollout restart failed: %s", err)
            return (
                f"set budget cap of route '{proposal.route}' from {before} to "
                f"${proposal.budget:.2f} in ConfigMap {self._configmap} "
                f"(proxy reload pending — rollout restart failed: {err})"
            )
        return (
            f"set budget cap of route '{proposal.route}' from {before} to "
            f"${proposal.budget:.2f} in ConfigMap {self._configmap}; "
            f"rolled Deployment/{self._deployment} to reload"
        )


def build_propose_budget_tool(
    gate: WriteGate,
    *,
    allowed_routes: set[str],
    min_budget: float,
    max_budget: float,
) -> Callable[..., str]:
    """Build the ``propose_budget`` callable bound to ``gate`` for MAF to expose.

    The domain guard (route allowlist / budget bounds) is enforced here, *before*
    the proposal is stored — a violating request is recorded via
    :meth:`WriteGate.deny` so it can never be approved.
    """

    def propose_budget(
        route: str,
        budget: float,
        rationale: str,
    ) -> str:
        """Propose changing a LiteLLM route's per-route budget cap. Does NOT execute.

        Call this whenever the user asks to raise, lower, set, or cap the budget
        (spend limit) of a routing lane/model. It records the proposal and
        returns a PENDING ticket. You MUST then show the user the proposal id and
        preview and ask them to approve or reject. NEVER claim the change
        happened — it has not been, and will not be, until the human approves.

        Args:
            route: the LiteLLM route (model_name) to re-budget (from the read tool).
            budget: the new per-route budget cap in USD (a non-negative number).
            rationale: one sentence on why this budget change is being proposed.

        Returns:
            A human-readable PENDING string with the proposal id and dry-run preview.
        """
        try:
            proposal = BudgetProposal(
                route=route,
                budget=budget,
                rationale=rationale,
                session_id=current_session_id.get(),
            )
        except Exception as exc:  # surface validation errors to the LLM as text
            LOG.warning("[write] propose rejected: %s", exc)
            return f"PROPOSAL REJECTED (not recorded): {exc}"

        # --- domain guard: bound route allowlist / budget range ---------------
        guard_reason: str | None = None
        if allowed_routes and route not in allowed_routes:
            allowed = ", ".join(sorted(allowed_routes))
            guard_reason = f"route '{route}' is not in the budget allowlist ({allowed})."
        elif not (min_budget <= budget <= max_budget):
            guard_reason = (
                f"budget ${budget:.2f} is outside the allowed range "
                f"[${min_budget:.2f}, ${max_budget:.2f}]."
            )
        if guard_reason is not None:
            proposal = gate.deny(proposal, guard_reason)
            return f"PROPOSAL DENIED: {guard_reason} No change was or will be made."

        proposal = gate.submit(proposal)
        if proposal.status == ProposalStatus.DENIED:
            return f"PROPOSAL DENIED: {proposal.outcome} No change was or will be made."

        return (
            f"PROPOSAL {proposal.id} recorded and is PENDING human approval — "
            f"nothing has been changed.\n"
            f"Intent: {proposal.human_summary()}\n"
            f"Rationale: {proposal.rationale}\n"
            f"Dry-run preview:\n{proposal.preview}\n\n"
            f"Tell the user exactly what will happen and ask them to Approve or "
            f"Reject proposal {proposal.id}. Do NOT say it is done."
        )

    return propose_budget

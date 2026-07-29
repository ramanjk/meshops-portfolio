# Iteration 2 (Gated Write + HITL) — Manual Test Cases (Pipeline)

*Audience: Ram (builder). These are the by-hand acceptance tests for the gated-write Pipeline Steward. They prove the three things that matter: (A) an approved promotion actually happens, (B) nothing happens without approval or when out of scope, (C) with the flag off the steward is exactly its read-only self. This is the demo-day script.*

## Preconditions

- The chat server running with **`WRITE_ENABLED=true`**. In-cluster (the live iter-2 deploy): `helm upgrade ... --set writeEnabled=true --set writeApprovalChannel=github_pr --set github.repo=ramanjk/meshops-portfolio` with the `github-token` Secret present.
- MLflow reachable for writes (`MLFLOW_TRACKING_URI`), with `phi-4-mini-meshops` seeded: v1 Archived, v2 Production, v3 Staging.
- Browser open on the Pipeline chat UI (LoadBalancer IP — the live iter-2 endpoint is **`http://52.249.59.40:8080/`**).
- **Startup proof:** `kubectl logs -n meshops deploy/hello-pipeline-iter2 | grep WRITE-ENABLED` shows *"HITL gate armed for model 'phi-4-mini-meshops' via 'github_pr' channel"*.

> **Read the first-principles story in [`01_use_case.md`](01_use_case.md) before demoing** — these steps are the concrete proof of the four defences described there.

---

## TC-P1 — Approve flow: "promote v3 to Production" (the headline demo)

| Step | Action | Expected |
|---|---|---|
| 1 | Ask: *"Promote phi-4-mini-meshops v3 from Staging to Production — it scores higher."* | Steward returns a proposal: the dry-run preview *"v3: Staging → Production (archive_existing=True). No change made (dry-run)"*, a proposal id `pw_…`, and (PR channel) a **"Review & merge PR to approve"** link. It does **not** claim the promotion happened. |
| 2 | Confirm nothing changed yet: ask *"what's in Production now?"* (or read MLflow) | Still **v2** in Production; v3 still Staging. |
| 3 | Open the linked PR → it's on branch `hitl/pw_…`, file `hitl-proposals/pw_….md`, body = the dry-run preview + proposal JSON + the merge=approve / close=reject note | The PR body matches the chat preview exactly. |
| 4 | **Merge** the PR (chat channel: click **Approve**) | Within `github.pollSeconds` (or after `curl -XPOST http://<chat>/reconcile`) the steward reports *"v3 is now in stage Production"*; MLflow shows v3 Production, v2 Archived. |
| 5 | Check pod logs for the audit line | `AUDIT` lines (`proposed`, then `executed`) with the proposal id, `kind":"registry-promotion"`, and `approver=<your-github-login>`. |

**Pass:** v3 moves to Production only *after* step 4, and the audit trail records proposal → execution.

---

## TC-P2 — Reject flow (close the PR)

| Step | Action | Expected |
|---|---|---|
| 1 | Ask for any transition (e.g. *"archive v1"*) | Proposal card / PR appears (id `pw_…`, preview). |
| 2 | **Close** the PR unmerged (chat: click **Reject**) | On next poll/`/reconcile`: `🚫 Rejected pw_…: no change was made.` |
| 3 | Verify registry | No change. Audit shows `proposed` then `rejected`. |
| 4 | Re-run `/reconcile` on the same closed PR | Idempotent — no second decision, no error; single-use enforced. |

**Pass:** closing/rejecting makes no change and the proposal cannot then be approved.

---

## TC-P3 — Out-of-scope model is denied at the applier

*The `propose_promotion` tool fixes `model_name` to `registered_model_name`, so the LLM cannot normally target another model. This case proves the **applier's** guard is the backstop even if a foreign proposal reached it.*

| Step | Action | Expected |
|---|---|---|
| 1 | (Unit-level) construct a `PromotionProposal(model_name="some-other-model", …)` and submit it | `MlflowApplier.preview`/`apply` raise `ApplyError(denied=True)` — *"model '…' is out of scope; only 'phi-4-mini-meshops' is writable."* → gate records **DENIED**. |
| 2 | Verify | Nothing transitioned; audit shows `denied`. |

**Pass:** even a foreign-model promotion is stopped by the single-model bound, not just the prompt. (Automated as `test_mlflow_applier_guards_foreign_model`.)

---

## TC-P4 — Bad target stage is rejected before it becomes a proposal

| Step | Action | Expected |
|---|---|---|
| 1 | Coax the steward to a nonsense stage (e.g. *"move v3 to stage 'Live'"*) | The tool returns **PROPOSAL REJECTED (not recorded)** — `to_stage` must be one of Staging/Production/Archived/None; **no card/PR** appears. |
| 2 | Verify | Nothing recorded or approvable. |

**Pass:** malformed intents never reach a human or MLflow. (Automated as `test_propose_promotion_tool_rejects_bad_stage`.)

---

## TC-P5 — TTL expiry

| Step | Action | Expected |
|---|---|---|
| 1 | Create a proposal, then wait past the TTL (`WRITE_PROPOSAL_TTL_SECONDS`; the PR channel auto-bumps to ≥ 7 days, so set it low to test) | — |
| 2 | Approve / merge | Error: proposal expired; no change made. Audit shows `expired`. |

**Pass:** stale proposals cannot be approved.

---

## TC-P6 — Read scope stays ungated

| Step | Action | Expected |
|---|---|---|
| 1 | Ask read questions: *"list all versions and their stages"*, *"what's the delta between Production and Staging?"*, *"why is v1 archived?"* | Answered directly from mlflow-mcp reads — **no card, no PR, no gate.** |

**Pass:** reads never trigger the gate (identical to the Iteration-1 answers you already validated).

---

## TC-P7 — Regression: flag OFF = read-only steward

| Step | Action | Expected |
|---|---|---|
| 1 | Point at `hello-pipeline-iter1` (or restart with `WRITE_ENABLED=false`) | — |
| 2 | Ask: *"promote v3 to Production"* | Steward **reasons but declines to act** — *"I observe and explain … I do not make or propose changes myself"* — exactly as Iteration 1. No `propose_promotion` tool exists; no `/approve` target. |
| 3 | `helm template helm/pipeline` (flag off) | No `WRITE_ENABLED` env, no `GITHUB_*`, no gated-write persona key. |

**Pass:** with the flag off the steward is byte-for-byte the read-only build (this is why `iter1` and `iter2` run side by side in the demo).

---

## Live smoke result already captured

The propose→PR path was validated live on `hello-pipeline-iter2` (2026-07-29): asking *"promote v3 Staging→Production"* produced proposal `pw_f9ce470b`, preview *"Staging → Production (archive_existing) — No change (dry-run)"*, and opened **PR #8** with **no MLflow change** until merge. (The test PR was closed afterwards.)

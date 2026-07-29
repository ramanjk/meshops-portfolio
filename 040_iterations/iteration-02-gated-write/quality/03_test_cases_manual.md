# Iteration 2 (Gated Write + HITL) — Manual Test Cases (Quality)

*Audience: Ram (builder). These are the by-hand acceptance tests for the gated-write Quality Steward. They prove: (A) an approved annotation actually happens, (B) nothing happens without approval or with bad input, (C) with the flag off the steward is exactly its read-only self. This is the demo-day script.*

## Preconditions

- The chat server running with **`WRITE_ENABLED=true`**. In-cluster (the live iter-2 deploy): `helm upgrade ... --set writeEnabled=true --set writeApprovalChannel=github_pr --set github.repo=ramanjk/meshops-portfolio` with the `github-token` Secret present.
- Langfuse reachable for writes with the project's public/secret key (already used for reads), and at least a few seeded traces + scores to point at.
- Browser open on the Quality chat UI (LoadBalancer IP — the live iter-2 endpoint is **`http://172.206.134.209:8080/`**).
- **Startup proof:** `kubectl logs -n meshops deploy/hello-quality-iter2 | grep WRITE-ENABLED` shows *"HITL gate armed for Langfuse annotations via 'github_pr' channel"*.

> **Read the first-principles story in [`01_use_case.md`](01_use_case.md) before demoing** — these steps are the concrete proof of the four defences described there.

---

## TC-Q1 — Approve flow: "flag this low-quality trace" (the headline demo)

| Step | Action | Expected |
|---|---|---|
| 1 | First, read: *"are there any low-scoring traces I should look at?"* → note a trace id it returns. Then: *"attach a faithfulness score of 0.55 to trace `<id>` — it's poorly grounded."* | Steward returns a proposal: the dry-run preview *"trace `<id>` (pipeline.steward.chat): will attach NUMERIC score 'faithfulness'=0.55. No change made (dry-run)"*, a proposal id `pw_…`, and (PR channel) a **"Review & merge PR to approve"** link. It does **not** claim the score was written. |
| 2 | Confirm nothing changed yet: open that trace in Langfuse | No new `faithfulness`=0.55 score on it. |
| 3 | Open the linked PR → branch `hitl/pw_…`, file `hitl-proposals/pw_….md`, body = preview + proposal JSON + merge=approve / close=reject note | The PR body matches the chat preview. |
| 4 | **Merge** the PR (chat channel: click **Approve**) | Within `github.pollSeconds` (or after `curl -XPOST http://<chat>/reconcile`) the steward reports *"score 'faithfulness'=0.55 attached to trace `<id>` (score id …)"*; the score now appears on that trace in Langfuse. |
| 5 | Check pod logs for the audit line | `AUDIT` lines (`proposed`, then `executed`) with the proposal id, `kind":"trace-annotation"`, and `approver=<your-github-login>`. |

**Pass:** the score appears only *after* step 4, and the audit trail records proposal → execution.

---

## TC-Q2 — Reject flow (close the PR)

| Step | Action | Expected |
|---|---|---|
| 1 | Propose any annotation | Proposal card / PR appears (id `pw_…`, preview). |
| 2 | **Close** the PR unmerged (chat: click **Reject**) | On next poll/`/reconcile`: `🚫 Rejected pw_…: no change was made.` |
| 3 | Verify Langfuse | No score written. Audit shows `proposed` then `rejected`. |
| 4 | Re-run `/reconcile` on the same closed PR | Idempotent — no second decision, no error; single-use enforced. |

**Pass:** closing/rejecting makes no change and the proposal cannot then be approved.

---

## TC-Q3 — Out-of-range value is rejected before it becomes a proposal

| Step | Action | Expected |
|---|---|---|
| 1 | Coax the steward to an invalid value (e.g. *"give trace `<id>` a score of 5"*) | The tool returns **PROPOSAL REJECTED (not recorded)** — `score_value` must be between 0.0 and 1.0; **no card/PR** appears. |
| 2 | Verify | Nothing recorded or approvable. |

**Pass:** malformed intents never reach a human or Langfuse. (Automated as `test_propose_annotation_tool_rejects_bad_value`.)

---

## TC-Q4 — Bad credentials / missing trace fail closed

| Step | Action | Expected |
|---|---|---|
| 1 | Propose an annotation on a non-existent trace id | The dry-run preview shows `(dry-run failed) trace … not found` — the proposal stays PENDING so you can judge/reject it, but an approve would fail closed. |
| 2 | (If the project keys were wrong) approve | `⛔ Denied` — Langfuse returns 401/403 → `ApplyError(denied=True)` → gate records **denied**; nothing written. |

**Pass:** a bad target or credential is surfaced honestly and never silently writes.

---

## TC-Q5 — TTL expiry

| Step | Action | Expected |
|---|---|---|
| 1 | Create a proposal, then wait past the TTL (the PR channel auto-bumps to ≥ 7 days, so set it low to test) | — |
| 2 | Approve / merge | Error: proposal expired; no change made. Audit shows `expired`. |

**Pass:** stale proposals cannot be approved.

---

## TC-Q6 — Read scope stays ungated

| Step | Action | Expected |
|---|---|---|
| 1 | Ask read questions: *"summarize recent eval scores"*, *"what's the quality trend?"*, *"what scores back the production model?"* | Answered directly from langfuse-mcp reads — **no card, no PR, no gate.** |

**Pass:** reads never trigger the gate (identical to the Iteration-1 answers you already validated).

---

## TC-Q7 — Regression: flag OFF = read-only steward

| Step | Action | Expected |
|---|---|---|
| 1 | Point at `hello-quality-iter1` (or restart with `WRITE_ENABLED=false`) | — |
| 2 | Ask: *"flag trace `<id>` as low quality"* | Steward **reasons but declines to act** — *"I do not take action — I simply monitor and report"* — exactly as Iteration 1. No `propose_annotation` tool; no `/approve` target. |
| 3 | `helm template helm/quality` (flag off) | No `WRITE_ENABLED` env, no `GITHUB_*`, no gated-write persona key. |

**Pass:** with the flag off the steward is byte-for-byte the read-only build (this is why `iter1` and `iter2` run side by side in the demo).

---

## Live smoke result already captured

The propose→PR path was validated live on `hello-quality-iter2` (2026-07-29): asking to *"attach a faithfulness score of 0.55 to the most recent trace"* produced proposal `pw_05397249`, preview *"will attach NUMERIC score 'faithfulness'=0.55. No change (dry-run)"*, and opened **PR #9** with **no Langfuse change** until merge. (The test PR was closed afterwards.)

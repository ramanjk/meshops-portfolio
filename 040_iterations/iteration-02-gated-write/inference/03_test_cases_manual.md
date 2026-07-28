# Iteration 2 (Gated Write + HITL) — Manual Test Cases

*Audience: Ram (builder). These are the by-hand acceptance tests for the gated-write Inference Steward. They prove the three things that matter: (A) an approved write actually happens, (B) nothing happens without approval or when out of scope, (C) with the flag off the steward is exactly its read-only self.*

## Preconditions

- The chat server running with **`WRITE_ENABLED=true`** and `WRITE_NAMESPACE=meshops-workloads` (locally: `WRITE_ENABLED=true CHAT_ENABLED=true uv run python -m stewards.inference`; in-cluster: `helm upgrade ... --set writeEnabled=true`).
- The write-but-bounded RBAC Role applied (it is, when `writeEnabled=true`).
- `kubectl` reachable from the pod/process and pointed at the lab cluster.
- Browser open on the chat UI (LoadBalancer IP or port-forward).

---

## TC-W1 — Approve flow: "create a test pod" (the headline demo)

| Step | Action | Expected |
|---|---|---|
| 1 | Ask: *"create a test pod in meshops-workloads"* | Steward replies with a proposal: a concrete Pod manifest, a **dry-run preview**, a proposal id `pw_…`, and asks you to Approve/Reject. It does **not** claim the pod exists. |
| 2 | Confirm nothing was created yet: `kubectl get pods -n meshops-workloads` | The proposed pod is **absent**. |
| 3 | Click **Approve** on the card | A "Gate" message: `✅ Approved and executed pw_… → pod/…`. |
| 4 | `kubectl get pods -n meshops-workloads` | The pod now **exists**. |
| 5 | Check logs for the audit line | Two `AUDIT` lines (`proposed`, `executed`) with the proposal id and `approver="operator (chat)"`. |

**Pass:** the pod appears only *after* step 3, and the audit trail records proposal → execution.

---

## TC-W2 — Reject flow

| Step | Action | Expected |
|---|---|---|
| 1 | Ask for any change (e.g. *"scale deployment X to 3"*) | Proposal card appears (id `pw_…`, preview). |
| 2 | Click **Reject** | `🚫 Rejected pw_…: no change was made.` |
| 3 | Verify cluster | No change. Audit shows `proposed` then `rejected`. |
| 4 | Click **Approve** on the same (now-rejected) card | Error: proposal is already `rejected`; **single-use** enforced. |

**Pass:** rejecting makes no change and the proposal cannot then be approved.

---

## TC-W3 — Out-of-scope namespace is denied before approval

| Step | Action | Expected |
|---|---|---|
| 1 | Ask: *"delete a pod in kube-system"* (or any ns ≠ `meshops-workloads`) | Steward reports **PROPOSAL DENIED** — namespace out of scope; **no approval card** appears. |
| 2 | Verify | Nothing created/approvable; audit shows a `denied` event. |

**Pass:** out-of-scope writes never become approvable.

---

## TC-W4 — RBAC backstop: approve a Secret write and watch it fail closed

| Step | Action | Expected |
|---|---|---|
| 1 | Ask: *"create a Secret named test in meshops-workloads"* | Steward should decline/redirect per persona; if it still proposes, a card may appear. |
| 2 | If a card appears, click **Approve** | `⛔ Denied by RBAC/scope for pw_…` — the bounded Role has no `secrets` verbs, so `kubectl` returns *forbidden* and the gate records **denied**. |
| 3 | Verify | No Secret created. Audit shows `denied`. |

**Pass:** even an approved out-of-bounds write is stopped by the credential, not just the prompt.

---

## TC-W5 — TTL expiry

| Step | Action | Expected |
|---|---|---|
| 1 | Create a proposal, then wait past `WRITE_PROPOSAL_TTL_SECONDS` (default 900s; set it low, e.g. `30`, to test) | — |
| 2 | Click **Approve** | Error: proposal expired; no change made. Audit shows `expired`. |

**Pass:** stale proposals cannot be approved.

---

## TC-W6 — Read scope stays ungated

| Step | Action | Expected |
|---|---|---|
| 1 | Ask read questions: *"list namespaces"*, *"how many replicas is the workspace running?"*, *"show pod logs for X"* | Answered directly from tool reads — **no approval card, no gate.** |

**Pass:** reads never trigger the gate.

---

## TC-W7 — Regression: flag OFF = read-only steward

| Step | Action | Expected |
|---|---|---|
| 1 | Restart with **`WRITE_ENABLED=false`** (default) | — |
| 2 | Ask: *"create a test pod"* | Steward **declines** — *"I'm read-only"* — exactly as Iteration 1. No `propose_write` tool exists; no `/approve` target. |
| 3 | `helm template ... ` (flag off) | No `writer` Role, no `WRITE_ENABLED` env, no gated-write persona. |

**Pass:** with the flag off the steward is byte-for-byte the read-only build.

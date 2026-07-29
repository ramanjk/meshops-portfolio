# Iteration 2 (Gated Write + HITL) — Automated Test Cases (Pipeline)

*Audience: Ram (builder). The gate's automated suite is **shared** across stewards and lives in [`tests/unit/test_hitl_gate.py`](../../../tests/unit/test_hitl_gate.py). It runs with `pytest -q` (no cluster, no LLM, no MLflow) using a `FakeApplier` (records calls; can simulate deny/transient-fail), a `FakeGitHubClient` (in-memory PRs, no network, no `gh`), and a controllable clock so TTL is deterministic.*

## Running

```bash
uv run pytest tests/unit/test_hitl_gate.py -q      # just the shared gate + both domains
uv run pytest -q                                    # full suite -> 88 passed
```

## What the shared gate tests lock down (apply to Pipeline too)

| Test | Invariant |
|---|---|
| `test_submit_previews_but_does_not_apply` | `submit` stores PENDING, runs **preview only** (dry-run), audits `proposed`. |
| `test_nothing_executes_without_approval` | proposing alone **never** calls `apply`. |
| `test_approve_executes_once_and_is_single_use` | `approve` runs `apply`, sets `EXECUTED`, records approver; a second `approve` raises (single-use). |
| `test_reject_never_applies` | `reject` sets `REJECTED` and never calls `apply`. |
| `test_denied_apply_fails_closed` | `ApplyError(denied=True)` → status `DENIED`, no crash. |
| `test_failed_apply_marked_failed` | a non-deny `ApplyError` → status `FAILED`. |
| `test_ttl_expiry_blocks_approval` | past TTL → not approvable, `approve` raises, status `EXPIRED`. |
| `test_deny_guard_records_but_never_stores_pending` | a domain-guard `deny` is audited but never approvable. |
| `test_pending_for_session_scopes_by_session` | approval cards don't leak across chat sessions. |
| `test_audit_sink_records_events` | every transition emits one structured `AUDIT` line. |

## GitHub-PR approval channel (shared)

| Test | Invariant |
|---|---|
| `test_pr_channel_opens_and_reconciles_merge` | `open` creates branch `hitl/<id>` + proposal file + PR, records `external_ref`/`external_id`; a **merged** PR → `sync` calls `gate.approve(merger)` → `EXECUTED`, applier ran once. |
| `test_pr_channel_close_rejects` | a **closed-unmerged** PR → `sync` calls `gate.reject` → `REJECTED`, nothing applied. |

## Pipeline-domain tests

| Test | Invariant |
|---|---|
| `test_promotion_proposal_summary_and_spec` | `PromotionProposal.human_summary()` / `spec_dict()` render the model/version/stage correctly. |
| `test_mlflow_applier_guards_foreign_model` | `MlflowApplier` denies (`ApplyError(denied=True)`) any proposal whose `model_name` ≠ `allowed_model`, at preview **and** apply — the single-model bound. |
| `test_propose_promotion_tool_records_pending` | the LLM tool records a proposal and returns a `PENDING` string (with `model_name` fixed to `allowed_model`). |
| `test_propose_promotion_tool_rejects_bad_stage` | an invalid `to_stage` returns `PROPOSAL REJECTED (not recorded)` — never stored, never approvable. |

## The two load-bearing assertions

1. **No execution without approval** — `test_nothing_executes_without_approval` + `test_approve_executes_once_and_is_single_use` together prove `apply` runs *iff* a human `approve`/merge happened, exactly once.
2. **Fails closed at the bound** — `test_mlflow_applier_guards_foreign_model` proves a promotion of the wrong model is recorded as `DENIED` and changes nothing, mirroring what the scoped MLflow credential enforces in production.

## Coverage notes / gaps

- The real `MlflowApplier` HTTP path (httpx against a live MLflow) is intentionally **not** unit-tested — the gate logic is covered via `FakeApplier`, and the live REST path is exercised by manual TC-P1. A future integration test could run it against an ephemeral MLflow server.
- The `GhCliClient` (`gh api`) subprocess path is likewise covered via `FakeGitHubClient`; the live `gh` path is exercised by manual TC-P1/TC-P2 (validated live on PR #8/#9).
- Endpoint wiring (`/approve`, `/reject`, `/reconcile`, cards) is exercised by the manual suite (`03_test_cases_manual.md`); a FastAPI `TestClient` test is a reasonable follow-up.

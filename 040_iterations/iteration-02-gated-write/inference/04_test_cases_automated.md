# Iteration 2 (Gated Write + HITL) — Automated Test Cases

*Audience: Ram (builder). The automated suite for the gate lives in [`tests/unit/test_write_gate.py`](../../../tests/unit/test_write_gate.py) and runs with `pytest -q` (no cluster, no LLM). It uses a `FakeApplier` (records calls, can simulate RBAC-deny/transient-fail) and a controllable `Clock` so TTL is deterministic.*

## Running

```bash
uv run pytest tests/unit/test_write_gate.py -q      # just the gate
uv run pytest -q                                     # full suite -> 61 passed
```

## What each test locks down

| Test | Invariant |
|---|---|
| `test_create_requires_manifest` | `create`/`apply` without a manifest is a `ValidationError`. |
| `test_scale_requires_name_and_replicas` | `scale` needs both `name` and `replicas`. |
| `test_replicas_out_of_bounds_rejected` | `replicas` is bounded (0–100). |
| `test_propose_records_pending_with_preview` | `propose` stores a PENDING proposal, runs **preview only** (dry-run), audits `proposed`. |
| `test_propose_out_of_scope_namespace_is_denied_not_stored` | wrong namespace → `DENIED`, never approvable (`approve` raises `KeyError`). |
| `test_approve_executes_once_then_single_use` | `approve` runs `apply`, sets `EXECUTED`, records approver; a second `approve` raises (single-use). |
| `test_nothing_executes_without_approval` | proposing alone **never** calls `apply`. |
| `test_reject_makes_no_change` | `reject` sets `REJECTED` and never calls `apply`. |
| `test_rbac_denied_apply_fails_closed` | `ApplyError(denied=True)` → status `DENIED`, outcome contains `forbidden`, no crash. |
| `test_apply_failure_marks_failed` | a non-deny `ApplyError` → status `FAILED`. |
| `test_expired_proposal_cannot_be_approved` | past TTL → not in `pending_for_session`, `approve` raises, `get` marks `EXPIRED`. |
| `test_pending_scoped_to_session` | `pending_for_session` isolates proposals per chat session. |
| `test_propose_write_tool_records_and_returns_pending` | the LLM tool records a proposal and returns a `PENDING` string. |
| `test_propose_write_tool_reports_denied_namespace` | the LLM tool returns `DENIED` for an out-of-scope namespace. |

## The two load-bearing assertions

1. **No execution without approval** — `test_nothing_executes_without_approval` + `test_approve_executes_once_then_single_use` together prove `apply` runs *iff* a human `approve` happened, exactly once.
2. **Fails closed at the credential** — `test_rbac_denied_apply_fails_closed` proves an approved-but-forbidden write is recorded as `DENIED` and changes nothing, mirroring what the namespaced RBAC Role enforces in-cluster.

## Coverage notes / gaps

- The `KubectlApplier` subprocess path is intentionally **not** unit-tested against a real cluster (it would need a live kube context). Its argv construction is simple and covered by manual TC-W1..W5. A future integration test could run it against `kind` with the bounded Role applied.
- Endpoint wiring (`/approve`, `/reject`, approval cards) is exercised by the manual suite (`03_test_cases_manual.md`); a FastAPI `TestClient` test is a reasonable follow-up.

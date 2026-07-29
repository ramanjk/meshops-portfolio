# Iteration 2 (Gated Write + HITL) — Automated Test Cases (Quality)

*Audience: Ram (builder). The gate's automated suite is **shared** across stewards and lives in [`tests/unit/test_hitl_gate.py`](../../../tests/unit/test_hitl_gate.py). It runs with `pytest -q` (no cluster, no LLM, no Langfuse) using a `FakeApplier`, a `FakeGitHubClient`, and a controllable clock. The shared gate + PR-channel tests are documented in the [pipeline automated guide](../pipeline/04_test_cases_automated.md); this page lists the **Quality-domain** tests.*

## Running

```bash
uv run pytest tests/unit/test_hitl_gate.py -q      # shared gate + both domains
uv run pytest -q                                    # full suite -> 88 passed
```

## Shared gate + channel tests (apply to Quality too)

The same ten gate-invariant tests (`test_submit_previews_but_does_not_apply`, `test_nothing_executes_without_approval`, `test_approve_executes_once_and_is_single_use`, `test_reject_never_applies`, `test_denied_apply_fails_closed`, `test_failed_apply_marked_failed`, `test_ttl_expiry_blocks_approval`, `test_deny_guard_records_but_never_stores_pending`, `test_pending_for_session_scopes_by_session`, `test_audit_sink_records_events`) and the two PR-channel tests (`test_pr_channel_opens_and_reconciles_merge`, `test_pr_channel_close_rejects`) exercise the exact `WriteGate`/`channels` code the Quality steward runs. See [pipeline §"What the shared gate tests lock down"](../pipeline/04_test_cases_automated.md).

## Quality-domain tests

| Test | Invariant |
|---|---|
| `test_annotation_proposal_summary_and_spec` | `AnnotationProposal.human_summary()` / `spec_dict()` render the trace/score name/value correctly (and truncate the trace id in the summary). |
| `test_annotation_value_bounds_enforced` | `score_value` outside `0.0–1.0` raises a `ValidationError` — the value bound. |
| `test_propose_annotation_tool_records_pending` | the LLM tool records a proposal and returns a `PENDING` string. |
| `test_propose_annotation_tool_rejects_bad_value` | an out-of-range `score_value` returns `PROPOSAL REJECTED (not recorded)` — never stored, never approvable. |

## The two load-bearing assertions

1. **No execution without approval** — the shared `test_nothing_executes_without_approval` + `test_approve_executes_once_and_is_single_use` prove `apply` runs *iff* a human `approve`/merge happened, exactly once — for the Quality applier as for any other.
2. **Fails closed at the bound** — `test_annotation_value_bounds_enforced` (schema) + the shared `test_denied_apply_fails_closed` (Langfuse 401/403 → `denied`) prove a malformed or unauthorized score changes nothing.

## Coverage notes / gaps

- The real `LangfuseApplier` HTTP path (httpx against a live Langfuse) is intentionally **not** unit-tested — the gate logic is covered via `FakeApplier`, and the live REST path is exercised by manual TC-Q1. A future integration test could run it against an ephemeral Langfuse.
- The `GhCliClient` (`gh api`) path is covered via `FakeGitHubClient`; the live `gh` path was exercised on PR #9.
- Endpoint wiring (`/approve`, `/reject`, `/reconcile`, cards) is exercised by the manual suite (`03_test_cases_manual.md`).

# Iteration 2 (Gated Write + HITL) — Automated Test Cases (Gateway)

*Audience: Ram (builder). The Gateway unit suite covers the read-only schema/settings/prompt loading and the gated route-budget domain guard. It also builds on the shared HITL gate suite documented by Pipeline, Quality, and SRE.*

## Running

```bash
uv run pytest tests/unit/test_gateway_settings.py tests/unit/test_gateway_schemas.py tests/unit/test_gateway_prompt_loading.py tests/unit/test_gateway_write.py -q
uv run pytest tests/unit/test_hitl_gate.py -q
```

The checkout contains **23 Gateway-specific unit tests** across the four Gateway files below, on top of the shared HITL gate tests (`tests/unit/test_write_gate.py`, `test_approval_channels.py`) that the gated-write path reuses. Full suite evidence captured for this steward: **134 passed**. Ruff parity remains unchanged (1 E501 CSS + S104).

## Gateway-specific tests

| File / test | What it proves |
|---|---|
| `test_gateway_settings.py::test_settings_load_with_required` | Required AOAI/Langfuse/LiteLLM settings load. |
| `test_gateway_settings.py::test_missing_required_raises` | Missing required config fails at boot. |
| `test_gateway_settings.py::test_allowed_route_set_parsing` | Comma-separated route allowlist parses cleanly. |
| `test_gateway_settings.py::test_empty_allowlist_is_unrestricted` | Empty allowlist means unrestricted within the LiteLLM config/RBAC scope. |
| `test_gateway_schemas.py::test_schema_version_pinned` | `SCHEMA_VERSION == 1.0.0`. |
| `test_gateway_schemas.py::test_valid_observation_round_trips` | Valid `GatewayObservation` serializes/deserializes. |
| `test_gateway_schemas.py::test_nullable_budgets` | Budget fields may be `null` when no caps are configured. |
| `test_gateway_schemas.py::test_negative_budget_rejected` | Budget caps cannot be negative. |
| `test_gateway_schemas.py::test_bad_posture_rejected` | Posture enum is `healthy|degraded|misconfigured`. |
| `test_gateway_schemas.py::test_misconfigured_requires_concern` | Misconfigured posture requires `budget_policy_concern=true`. |
| `test_gateway_schemas.py::test_misconfigured_with_concern_ok` | Misconfigured posture is valid when the concern flag is set. |
| `test_gateway_schemas.py::test_health_accounting_must_be_consistent` | Healthy + unhealthy route counts cannot exceed routes observed. |
| `test_gateway_schemas.py::test_requires_hitl_true_is_rejected` | Third no-write guarantee: read-only schema rejects HITL. |
| `test_gateway_schemas.py::test_no_extra_fields` | Extra fields are not accepted by the schema. |
| `test_gateway_prompt_loading.py::test_read_prompt_returns_repo_prompt_content` | Prompt loading finds repo prompt content. |
| `test_gateway_prompt_loading.py::test_gated_write_persona_present` | Gated-write persona exists and says propose/approve. |
| `test_gateway_prompt_loading.py::test_empty_in_cluster_prompt_falls_back` | Blank mounted prompt cannot shadow image-baked prompt. |
| `test_gateway_write.py::test_proposal_human_summary_and_spec` | `BudgetProposal` summary/spec/audit kind are correct. |
| `test_gateway_write.py::test_valid_budget_becomes_pending_then_executes` | Valid budget change becomes PENDING, then executes on approval. |
| `test_gateway_write.py::test_route_not_in_allowlist_denied` | Route allowlist denies before pending. |
| `test_gateway_write.py::test_budget_out_of_range_denied` | Budget bound denies/rejects before pending. |
| `test_gateway_write.py::test_empty_allowlist_permits_any_route` | Empty allowlist permits any route within the config/RBAC scope. |
| `test_gateway_write.py::test_denied_proposal_cannot_be_approved` | Denied proposals leave nothing approvable. |

## Shared HITL gate tests Gateway builds on

| Test | Invariant |
|---|---|
| `test_submit_previews_but_does_not_apply` | `submit` stores PENDING and runs preview only. |
| `test_nothing_executes_without_approval` | Proposal alone never calls `apply`. |
| `test_approve_executes_once_and_is_single_use` | Approval executes exactly once. |
| `test_reject_never_applies` | Rejection never applies. |
| `test_denied_apply_fails_closed` | `ApplyError(denied=True)` records DENIED. |
| `test_failed_apply_marked_failed` | Transient apply error records FAILED. |
| `test_ttl_expiry_blocks_approval` | Expired proposal cannot be approved. |
| `test_deny_guard_records_but_never_stores_pending` | Domain-denied proposals are audited but not pending. |
| `test_pending_for_session_scopes_by_session` | Pending cards are session-scoped. |
| `test_audit_sink_records_events` | Proposal/decision/outcome emit audit records. |
| `test_pr_channel_opens_and_reconciles_merge` | Merged PR approves and executes. |
| `test_pr_channel_close_rejects` | Closed-unmerged PR rejects and does not apply. |

## The two load-bearing assertions

1. **No execution without approval** — shared gate tests plus `test_valid_budget_becomes_pending_then_executes` prove `apply` runs only after approval.
2. **Fails closed at Gateway bounds** — route allowlist and budget guard tests prove bad proposals never become approvable.

## Coverage notes / gaps

- Real `kubectl` ConfigMap patch and `rollout restart` execution are covered by live manual TC-GW-5, not unit tests.
- The `gh` CLI path is covered by shared fake GitHub client tests plus live PR #15.
- Endpoint wiring (`/reconcile`, poll loop) is primarily manual/integration coverage.

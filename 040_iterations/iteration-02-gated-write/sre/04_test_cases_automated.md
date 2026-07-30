# Iteration 2 (Gated Write + HITL) — Automated Test Cases (SRE)

*Audience: Ram (builder). The SRE unit suite covers the read-only schema/settings/prompt loading and the gated Deployment-scale domain guard. It also builds on the shared HITL gate suite documented by Pipeline and Quality.*

## Running

```bash
uv run pytest tests/unit/test_sre_settings.py tests/unit/test_sre_schemas.py tests/unit/test_sre_prompt_loading.py tests/unit/test_sre_write.py -q
uv run pytest tests/unit/test_hitl_gate.py -q
```

The checkout contains **23 SRE-specific unit tests** across the four SRE files below, on top of the shared HITL gate tests (`tests/unit/test_write_gate.py`, `test_approval_channels.py`) that the gated-write path reuses.

## SRE-specific tests

| File / test | What it proves |
|---|---|
| `test_sre_settings.py::test_settings_load_with_required` | Required AOAI/Langfuse/AKS/Prometheus settings load. |
| `test_sre_settings.py::test_missing_required_raises` | Missing required config fails at boot. |
| `test_sre_settings.py::test_allowed_deployment_set_parsing` | Comma-separated scale allowlist parses cleanly. |
| `test_sre_settings.py::test_empty_allowlist_is_unrestricted` | Empty allowlist means unrestricted within namespace. |
| `test_sre_schemas.py::test_schema_version_pinned` | `SCHEMA_VERSION == 1.0.0`. |
| `test_sre_schemas.py::test_valid_observation_round_trips` | Valid `IncidentObservation` serializes/deserializes. |
| `test_sre_schemas.py::test_nullable_metrics` | GPU/error fields may be `null` when not measurable. |
| `test_sre_schemas.py::test_gpu_out_of_range_rejected` | GPU percent is bounded to `[0,100]`. |
| `test_sre_schemas.py::test_bad_severity_rejected` | Severity enum is `none|low|medium|high`. |
| `test_sre_schemas.py::test_high_severity_requires_incident` | High severity cannot be claimed without `incident_suspected=true`. |
| `test_sre_schemas.py::test_high_severity_with_incident_ok` | High severity is valid when incident is suspected. |
| `test_sre_schemas.py::test_requires_hitl_true_is_rejected` | Third no-write guarantee: read-only schema rejects HITL. |
| `test_sre_schemas.py::test_no_extra_fields` | Extra fields are not accepted by the schema. |
| `test_sre_prompt_loading.py::test_read_prompt_returns_repo_prompt_content` | Prompt loading finds repo prompt content. |
| `test_sre_prompt_loading.py::test_gated_write_persona_present` | Gated-write persona exists and says propose/approve. |
| `test_sre_prompt_loading.py::test_empty_in_cluster_prompt_falls_back` | Blank mounted prompt cannot shadow image-baked prompt. |
| `test_sre_write.py::test_proposal_human_summary_and_spec` | `ScaleProposal` summary/spec/audit kind are correct. |
| `test_sre_write.py::test_valid_scale_becomes_pending_then_executes` | Valid scale becomes PENDING, then executes on approval. |
| `test_sre_write.py::test_out_of_scope_namespace_denied` | Namespace guard denies before pending. |
| `test_sre_write.py::test_deployment_not_in_allowlist_denied` | Deployment allowlist denies before pending. |
| `test_sre_write.py::test_replicas_out_of_range_denied` | Replica bound denies/rejects before pending. |
| `test_sre_write.py::test_empty_allowlist_permits_any_deployment_in_namespace` | Empty allowlist permits any deployment in allowed namespace. |
| `test_sre_write.py::test_denied_proposal_cannot_be_approved` | Denied proposals leave nothing approvable. |

## Shared HITL gate tests SRE builds on

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

1. **No execution without approval** — shared gate tests plus `test_valid_scale_becomes_pending_then_executes` prove `apply` runs only after approval.
2. **Fails closed at SRE bounds** — namespace, allowlist, and replica guard tests prove bad proposals never become approvable.

## Coverage notes / gaps

- Real `kubectl` subprocess execution is covered by live manual TC-SRE-5, not unit tests.
- The `gh` CLI path is covered by shared fake GitHub client tests plus live PR #14.
- Endpoint wiring (`/reconcile`, poll loop) is primarily manual/integration coverage.

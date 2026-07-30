# Iteration 2 (Gated Write + HITL) — Automated Test Cases (Security)

*Audience: Ram (builder). The Security unit suite covers the read-only schema/settings/prompt loading and the gated PR-quarantine domain guard. It also builds on the shared HITL gate suite documented by Pipeline, Quality, SRE, and Gateway.*

## Running

```bash
uv run pytest tests/unit/test_security_settings.py tests/unit/test_security_schemas.py tests/unit/test_security_prompt_loading.py tests/unit/test_security_write.py -q
uv run pytest tests/unit/test_hitl_gate.py -q
```

The checkout contains **25 Security-specific unit tests** across the four Security files below. Full suite evidence captured for this steward: **159 passed**. Ruff parity remains unchanged: **1 E501** (button CSS in `serve.py`) + **S104** (`uvicorn` on `0.0.0.0`), same baseline as every steward.

## Security-specific tests

| File / test | What it proves |
|---|---|
| `test_security_settings.py::test_settings_load_with_required` | Required AOAI/Langfuse/GitHub settings load. |
| `test_security_settings.py::test_missing_required_raises` | Missing required config fails at boot. |
| `test_security_settings.py::test_allowed_label_set_and_default` | Comma-separated quarantine label allowlist parses and first label is default. |
| `test_security_settings.py::test_default_label_fallback` | Empty label config falls back to `quarantined`. |
| `test_security_schemas.py::test_schema_version_pinned` | `SCHEMA_VERSION == 1.0.0`. |
| `test_security_schemas.py::test_valid_observation_round_trips` | Valid `SecurityObservation` serializes/deserializes. |
| `test_security_schemas.py::test_negative_count_rejected` | Classification counts cannot be negative. |
| `test_security_schemas.py::test_bad_threat_rejected` | Threat enum is `none|prompt_injection|confused_deputy|data_poisoning|other`. |
| `test_security_schemas.py::test_bad_risk_rejected` | Risk enum is `none|low|medium|high|critical`. |
| `test_security_schemas.py::test_dominant_threat_requires_suspicion` | A non-`none` dominant threat requires `threat_suspected=true`. |
| `test_security_schemas.py::test_high_risk_requires_suspicion` | High/critical risk requires `threat_suspected=true`. |
| `test_security_schemas.py::test_malicious_finding_ok` | A malicious/high-risk finding is valid when suspicion and accounting agree. |
| `test_security_schemas.py::test_classification_accounting_must_be_consistent` | Benign + suspicious + malicious cannot exceed inputs observed. |
| `test_security_schemas.py::test_requires_hitl_true_is_rejected` | Third no-write guarantee: read-only schema rejects HITL. |
| `test_security_schemas.py::test_no_extra_fields` | Extra fields are not accepted by the schema. |
| `test_security_prompt_loading.py::test_read_prompt_returns_repo_prompt_content` | Prompt loading finds repo prompt content. |
| `test_security_prompt_loading.py::test_gated_write_persona_present` | Gated-write persona exists and says propose/approve. |
| `test_security_prompt_loading.py::test_empty_in_cluster_prompt_falls_back` | Blank mounted prompt cannot shadow image-baked prompt. |
| `test_security_write.py::test_proposal_human_summary_and_spec` | `QuarantineProposal` summary/spec/audit kind are correct. |
| `test_security_write.py::test_valid_quarantine_becomes_pending_then_executes` | Valid quarantine becomes PENDING, then executes on approval. |
| `test_security_write.py::test_default_label_used_when_omitted` | The default label is used when caller omits one. |
| `test_security_write.py::test_label_not_in_allowlist_denied` | Label allowlist denies before pending. |
| `test_security_write.py::test_invalid_pr_number_rejected_at_construction` | Invalid PR numbers fail validation. |
| `test_security_write.py::test_empty_allowlist_permits_any_label` | Empty allowlist permits any label. |
| `test_security_write.py::test_denied_proposal_cannot_be_approved` | Denied proposals leave nothing approvable. |

## Shared HITL gate tests Security builds on

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
| `test_pr_channel_opens_and_reconciles_merge` | `github_pr` channel remains available if chosen. |
| `test_pr_channel_close_rejects` | Closed-unmerged PR rejects and does not apply. |

## The two load-bearing assertions

1. **No execution without approval** — shared gate tests plus the Security write lifecycle prove the GitHub label write runs only after approval.
2. **Fails closed at Security bounds** — label allowlist and denied-proposal tests prove bad labels never become approvable.

## Coverage notes / gaps

- Real GitHub label application and audit comment are covered by live manual TC-W-2/3, not unit tests.
- The chat UI `/approve` path is covered by live manual tests plus shared gate unit tests.
- No-cluster-write RBAC is live authorization evidence, not a Python unit test.

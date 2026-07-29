# HITL write proposal `pw_f9ce470b`

**Intent:** promote phi-4-mini-meshops v3 → Production

**Rationale:** Promote version 3 to Production since its eval accuracy (0.86) is higher than the current Production version.

> Merging this PR **approves** the write; closing it **rejects** it. The steward's deterministic executor applies it in-process under its own bounded credentials (ADR-0011) — the PR is the approval signal, not the actuator.

## Dry-run preview

```
model-version phi-4-mini-meshops v3: Staging → Production (archive_existing=True). No change made (dry-run).
```

## Proposal

```json
{
  "model_name": "phi-4-mini-meshops",
  "version": 3,
  "to_stage": "Production",
  "archive_existing": true
}
```

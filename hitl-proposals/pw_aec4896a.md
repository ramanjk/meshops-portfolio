# HITL write proposal `pw_aec4896a`

**Intent:** set budget cap of route 'chat-economy' to $12.00

**Rationale:** The chat-economy lane keeps hitting its spend cap; raising it to $12 will allow more usage.

> Merging this PR **approves** the write; closing it **rejects** it. The steward's deterministic executor applies it in-process under its own bounded credentials (ADR-0011) — the PR is the approval signal, not the actuator.

## Dry-run preview

```
LiteLLM route 'chat-economy': budget cap 5.0 -> $12.00. No change made (dry-run).
```

## Proposal

```json
{
  "kind": "LiteLLMRouteBudget",
  "route": "chat-economy",
  "max_budget": 12.0
}
```

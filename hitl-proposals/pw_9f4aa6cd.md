# HITL write proposal `pw_9f4aa6cd`

**Intent:** set budget cap of route 'chat-economy' to $20.00

**Rationale:** User requested a higher per-route budget to allow more spend on chat-economy.

> Merging this PR **approves** the write; closing it **rejects** it. The steward's deterministic executor applies it in-process under its own bounded credentials (ADR-0011) — the PR is the approval signal, not the actuator.

## Dry-run preview

```
LiteLLM route 'chat-economy': budget cap 12.0 -> $20.00. No change made (dry-run).
```

## Proposal

```json
{
  "kind": "LiteLLMRouteBudget",
  "route": "chat-economy",
  "max_budget": 20.0
}
```

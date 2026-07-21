# ADR-0001: Adopt the six-steward mesh as the MeshOps operations substrate

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

MeshOps is positioned in `035_others/vision.md` as a *mesh-based operations discipline* whose substance is not one super-agent but a coordinated set of specialist agents — "stewards" — each owning one operational concern (LLMOps serving, MLOps, LLMOps eval, AIOps, LLMOps routing, SecOps). The roadmap (`035_others/ai-career-roadmap.md`) and use-cases doc both assume this partition is fixed for P0–P4.

Three forces pin the choice:

1. **Hiring positioning.** A multi-agent mesh hits more keywords for AI Platform / MLOps / LLMOps roles than a single Copilot-style agent and differentiates from the archived AKS Copilot project.
2. **Accountability.** Per `CLAUDE.md` §Steward conventions, every use case must declare a driving steward; co-ownership is forbidden. That contract requires a small, named roster.
3. **Locked Phase scope.** P0–P4 of the roadmap are sized around six stewards. A seventh — or a fluid count — would require re-pacing every phase.

This is the first MeshOps ADR. Numbering restarts at 0001 per `CLAUDE.md`.

## Decision

We adopt a **mesh of exactly six stewards** as the operations substrate for MeshOps Phases 0 through 4:

| Steward | Owns | -Ops surface |
|---|---|---|
| Inference | KAITO Workspace lifecycle, vLLM tuning, LLM↔SLM routing | LLMOps (serving) |
| Pipeline | Fine-tune → eval → registry promotion | MLOps |
| Quality | Ragas / Promptfoo / Foundry-eval, drift, prompt PRs | LLMOps (quality) |
| SRE | Prom + Langfuse correlation, scaler tuning, postmortems | AIOps |
| Gateway | LiteLLM / Envoy AI Gateway, A/B routes, budgets | LLMOps (routing/cost) |
| Security | Prompt-injection-through-cluster-state, MCP confused-deputy, RAG poisoning | SecOps |

Adding a seventh steward requires its own ADR with an explicit *"why-not-an-existing-steward"* justification.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) Six specialist stewards (chosen)** | Clear accountability; one steward per -Ops surface; hits the multi-agent hiring keywords; matches roadmap phasing | Higher coordination overhead than (b); needs a group-chat orchestrator | **Chosen** |
| (b) One supervisor agent with tools (AKS Copilot pattern) | Lowest complexity; faster to ship | Doesn't demonstrate multi-agent; weaker -Ops surface coverage | Rejected — single-agent pattern |
| (c) Four-steward mesh (collapse SRE into Inference, Security into Quality) | Faster Phase 1 | Loses AIOps surface explicitly; muddies SecOps accountability; reverses a key vision claim | Rejected — breaks "every phase ships on every -Ops surface" rule |
| (d) Open-ended steward roster ("add as needed") | Maximum flexibility | No accountability anchor; phase planning becomes impossible; hiring narrative dilutes | Rejected — accountability over flexibility for v1 |

## Consequences

**Positive:**

- Every use case in `035_others/use-cases.md` has exactly one driving steward.
- Roadmap phases stay pace-stable because the roster doesn't shift.
- Cross-steward flows (X-1, X-2, X-3) have a finite combinatorial surface.
- Threat model can enumerate inter-steward attack chains exhaustively.

**Negative / accepted trade-offs:**

- A use case that *would* fit a hypothetical seventh steward (e.g., a Data steward for the runbook corpus) has to be assigned to an existing steward — currently Security owns RAG corpus integrity, which is a stretch.
- Group-chat orchestration overhead is real; (b) supervisor would have lower latency.

**Things we'll need to revisit:**

- Whether Quality should split into "eval" and "prompt-PR" stewards in P5+ as the eval surface grows.
- Whether a Data Steward becomes warranted once the RAG corpus exceeds a synthetic size — would need its own ADR.

## References

- `035_others/vision.md` §1 — mission anchoring the mesh framing.
- `035_others/agent-catalog.md` — per-steward responsibilities.
- `035_others/ai-career-roadmap.md` §2 — phase-by-phase deliverable matrix tied to the six stewards.
- `035_others/use-cases.md` §2 — six per-steward UCs.
- `CLAUDE.md` §Steward conventions — accountability rule.

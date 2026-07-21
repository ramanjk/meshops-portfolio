# ADR-0002: Split agent runtime — Microsoft Agent Framework for five stewards, Foundry Agent Service for Quality

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

Microsoft ships two related agent runtimes that overlap heavily:

- **Microsoft Agent Framework (MAF)** — open-source Python / .NET library, v1.0 GA in April 2026. You host the process yourself (typically as a pod on AKS). Built-in OpenTelemetry tracing emitting GenAI semantic conventions. Group-chat / handoff / workflow patterns built in.
- **Azure AI Foundry Agent Service** — managed agent runtime inside Azure AI Foundry. Microsoft hosts the process; you configure the agent, prompts, tools, evals via the Foundry portal or API.

MeshOps's portfolio narrative wants Ram to demonstrate *both* — managed-runtime fluency and self-hosted fluency. Picking only one would leave a JD-keyword gap. But running every steward on both would double the operational load with no learning gain.

The forces:

- Quality Steward's loop (drift detection → eval → prompt-PR) maps unusually well onto Foundry's managed eval surface (Foundry Evaluations + Prompt Flow).
- The remaining stewards (Inference, Pipeline, SRE, Gateway, Security) are tightly coupled to AKS/K8s state and want to live next to that state in the same cluster.
- Iteration-01 (this iteration) ships only the Inference Steward, on MAF — so the Foundry side of the split is realised in P1, not now. The ADR still belongs in this iteration because the *decision* is binding from day 1.

## Decision

Five stewards run on **Microsoft Agent Framework (Python)** as AKS pods in the portfolio cluster: Inference, Pipeline, SRE, Gateway, Security. One steward — **Quality** — runs on **Azure AI Foundry Agent Service** as a managed agent. Cross-runtime communication goes through the same MCP tool layer plus a thin MAF group-chat bridge in the portfolio cluster.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) MAF for 5, Foundry Agent Service for Quality (chosen)** | Demonstrates both runtimes; Quality's managed-eval affinity gets used; minimal added ops cost (one steward only) | One steward sits outside the AKS pod plane; group-chat bridge needs care | **Chosen** |
| (b) All six on MAF | Uniform ops + deployment story; simpler debug | Misses managed-runtime demo; doesn't exercise Foundry Agent Service which is on the AI-300 surface | Rejected — narrows hiring narrative |
| (c) All six on Foundry Agent Service | Showcases Foundry maximally | Stewards lose the "in the same cluster as the workload" intimacy; harder to reach AKS-MCP from a managed runtime; less control over the steward loop | Rejected — strategy intimacy with AKS lost |
| (d) AutoGen / LangGraph / CrewAI for some stewards as a "framework taster" | Demonstrates breadth | Multi-framework Babel; doesn't fit hiring positioning ("Microsoft AI stack end-to-end") | Rejected — `related-work.md` already settles this |

## Consequences

**Positive:**

- AI-300 cert positioning is reinforced (Foundry Agent Service + Foundry Evals are on its surface).
- Quality Steward's eval-heavy loop benefits from Foundry's managed eval infrastructure rather than re-implementing it.
- Five stewards on MAF means cluster-affinity tools (kubectl, KAITO CR ops) stay first-class.

**Negative / accepted trade-offs:**

- One steward is on a different runtime, so its observability and IAM story is unique to it.
- Group-chat bridge between cluster MAF orchestrator and Foundry-hosted Quality needs care — initially via MCP only (Quality reaches in via Langfuse-MCP + Foundry-MCP).

**Things we'll need to revisit:**

- Whether Foundry Agent Service exposes the right hooks for Quality's prompt-PR flow once it ships its 2026-Q3 features.
- Whether the second Foundry-hosted steward makes sense in P4 (currently no — five-on-MAF / one-on-Foundry is the locked split).

## References

- `035_others/architecture.md` §7 — component-to-runtime table.
- `035_others/agent-catalog.md` §5 — Quality Steward runtime call-out.
- [Microsoft Agent Framework 1.0 announcement](https://devblogs.microsoft.com/agent-framework/microsoft-agent-framework-version-1-0/).
- [Azure AI Foundry Agent Service](https://learn.microsoft.com/en-us/azure/ai-foundry/agents/).
- `035_others/related-work.md` §2 — AutoGen / LangGraph / CrewAI comparison.

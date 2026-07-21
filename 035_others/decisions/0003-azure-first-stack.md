# ADR-0003: Adopt an Azure-first stack — AKS, Azure OpenAI, Azure AI Foundry — and reject multi-cloud portability

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

Two forces shape the cloud-portability question:

- **Career positioning.** Ram is a Microsoft employee targeting internal mobility into AI Platform / MLOps / LLMOps roles, primarily inside Microsoft (`035_others/vision.md` §4). A multi-cloud project would dilute the "I can ship in your stack" signal.
- **Cost lever.** Ram has unlimited Azure OpenAI + Foundry + GitHub Copilot quota through his Microsoft tenant (auto-memory `ram-microsoft-resources`). That is a real, unique cost-of-experimentation advantage that disappears if we make ourselves cloud-agnostic.

Plus a technical force: KAITO is *the* AKS-native LLM/SLM operator; on EKS or GKE we would be re-tooling on `vLLM Production Stack` or `KServe + llm-d`, which are alternative substrates with their own learning curves. Doing both halves the depth.

## Decision

MeshOps is **Azure-only** through Phase 4. Specifically:

- **Cluster:** Azure Kubernetes Service (AKS) only. No EKS / GKE / on-prem.
- **Steward inference:** Azure OpenAI Service via the v1 GA API; `gpt-4.1` deployment by default.
- **Managed agent:** Azure AI Foundry Agent Service (for the Quality Steward per ADR-0002).
- **Inference workloads:** KAITO Workspaces on AKS GPU nodepool.
- **Identity:** Microsoft Entra ID; AKS Workload Identity for pods.
- **Container registry:** Azure Container Registry.
- **Cluster observability:** Azure Managed Prometheus + Azure Managed Grafana (ADR-0006).

Code is written so individual components can be swapped if necessary, but **no engineering work is spent achieving cross-cloud portability** in v1.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) Azure-only end-to-end (chosen)** | Aligns with Microsoft hiring narrative; leverages unlimited tenant quota; KAITO is AKS-managed | Single-cloud lock-in (acceptable for portfolio scope) | **Chosen** |
| (b) Multi-cloud (AKS + EKS) | Demonstrates portability | Halves the depth on each cloud; dilutes hiring narrative; no quota advantage outside Azure | Rejected — wrong target audience |
| (c) Cloud-agnostic K8s (vanilla manifests only, no Azure-specific add-ons) | Maximum portability | Loses Workload Identity convenience, Managed Prom, Managed Grafana, AKS-MCP, KAITO add-on; reinvents | Rejected — gives up the substrate's value |
| (d) Self-hosted everything on bare-metal | Most control | No upside for portfolio; massive ops cost | Rejected — out of scope |

## Consequences

**Positive:**

- Hiring narrative cohesion: "Microsoft AI stack end-to-end."
- $0-to-Ram inference cost via tenant quota.
- KAITO + Foundry Agent Service + AKS-MCP all come for free as managed add-ons / managed services.

**Negative / accepted trade-offs:**

- A non-Azure reviewer can't run iteration-01 on their cloud without significant rewrites.
- If Microsoft deprecates Foundry Agent Service or pivots Azure OpenAI's API surface, MeshOps absorbs the migration cost.

**Things we'll need to revisit:**

- If the AI-300 cert succession introduces a new Microsoft AI cert with a different stack opinion, re-validate.
- Cross-cloud portability can be added as a *demonstration* exercise post-P4 (advanced track) without changing v1.

## References

- `035_others/vision.md` §4 — "why Ram now."
- `035_others/cost-and-deployment.md` §2 — $0-to-Ram Azure OpenAI assumption.
- `035_others/related-work.md` §3 — "MeshOps is AKS-native by design."
- auto-memory `ram-microsoft-resources` — MS tenant quota.
- [Azure OpenAI v1 GA API](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle).

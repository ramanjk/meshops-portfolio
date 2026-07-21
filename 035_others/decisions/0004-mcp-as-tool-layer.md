# ADR-0004: Use Model Context Protocol (MCP) as the single tool layer — no bespoke SDK wrappers

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

Stewards need to reach a long list of external systems: AKS (kubectl + Azure Resource Manager), GitHub, Azure AI Foundry, Prometheus, Langfuse, LiteLLM, Kubeflow, MLflow, Defender for Cloud. The classic agent pattern is to write a Python wrapper per system and register each wrapper as a tool. That works, but it scales badly for a six-steward mesh:

- **Permission stories diverge.** Each wrapper invents its own auth/RBAC translation.
- **Audit gets fragmented.** Each wrapper emits its own logs in its own shape.
- **Confused-deputy defence is per-wrapper.** Defence-in-depth becomes copy-paste.
- **Cross-steward consistency erodes.** When two stewards call the same system from different code paths, behaviour drifts.

Model Context Protocol (`modelcontextprotocol.io`, now a Linux Foundation project) solves this. An MCP server exposes a typed tool surface; an MCP client (the agent) discovers tools at runtime; capability scoping, schema validation, and audit can all live server-side once.

Microsoft has been investing in first-party MCP servers — `Azure/aks-mcp` is the load-bearing one for MeshOps and is a Microsoft-OSS Go binary with a Helm chart (Microsoft Learn, 2026-02-18). Azure's general-purpose `Azure MCP Server` covers the broader Azure surface, and GitHub publishes `github/github-mcp-server`.

Iteration-01 wires the AKS-MCP server (read-only) and a tiny in-repo Prom-MCP shim. The decision to adopt MCP *as a class* is independent of iteration-01's narrow tool set.

## Decision

All steward → external-system tool calls go through **MCP servers**. The mesh ships **no bespoke SDK wrappers** for ARM / kubectl / GitHub / Prometheus / Langfuse / LiteLLM / Kubeflow / MLflow / Defender.

The MCP servers MeshOps uses in v1:

| MCP server | Source | Status 2026-05-26 |
|---|---|---|
| AKS-MCP | `github.com/Azure/aks-mcp` (Microsoft OSS) | Available; v0.0.18 |
| GitHub-MCP | `github.com/github/github-mcp-server` | Available |
| Foundry-MCP | Subset of `microsoft/azure-mcp` | Available |
| Prom-MCP | In-repo shim (iteration-01) | Authored here; candidate for upstream contribution |
| Langfuse-MCP | Community | Status uncertain; in-repo shim if absent |
| LiteLLM-MCP | LiteLLM project | Available |
| Kubeflow-MCP / MLflow-MCP | Community / TBD | Status uncertain; SDK fallback documented case-by-case |
| Defender-MCP | Subset of `microsoft/azure-mcp` | Available |

**If a needed capability is not in MCP**, the response is to author a missing MCP server (candidate for KAITO upstream / community contribution), not to write a bespoke SDK wrapper inside the steward.

Stewards declare a signed **capability manifest** listing the MCP tools they may call; the MCP server enforces this server-side.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) MCP for everything (chosen)** | Uniform auth + audit + capability; aligns with Linux Foundation MCP momentum; lets MeshOps contribute upstream | Some MCP servers don't exist yet — we author them or fall back to in-repo shims | **Chosen** |
| (b) Per-steward Python SDK wrappers | Each wrapper can be tuned per steward; no MCP-server hop | Audit fragments; confused-deputy defence has to be per wrapper; no upstream contribution path | Rejected — accountability + audit lose |
| (c) Hybrid (MCP for the big ones, SDK wrappers for niche ones) | Pragmatic | Same fragmentation problem at smaller scale; tempts everyone to write wrappers "just this once" | Rejected — slippery slope |
| (d) LangChain Tool ecosystem | Mature, broad | Locks us to LangChain framework rather than MCP-as-a-standard; cross-runtime portability harder | Rejected — framework lock-in over standards-based |

## Consequences

**Positive:**

- All inter-system access is auditable in one place — see `035_others/planes-and-mcp.md` §5.
- A new steward inherits capability scoping for free.
- KAITO upstream PR track (ADR-0012 in P1) has a natural home: missing MCP servers are upstream candidates.
- The confused-deputy defence (`planes-and-mcp.md` §4) has exactly one place to live.

**Negative / accepted trade-offs:**

- Two missing MCP servers (Prom-MCP, Langfuse-MCP) need authoring effort. Iteration-01 authors the Prom-MCP shim (minimal one-tool surface) to seed this.
- Tool discovery is dynamic — a steward's behaviour depends on what the server advertised at handshake time. Mitigated by signed manifests.

**Things we'll need to revisit:**

- If a future Microsoft / Foundry MCP server obsoletes our in-repo Prom-MCP, retire ours.
- If MCP itself evolves a breaking spec change (e.g., transport semantics), pin SDK versions per steward.

## References

- [Model Context Protocol spec](https://modelcontextprotocol.io/specification).
- [Azure/aks-mcp](https://github.com/Azure/aks-mcp) v0.0.18.
- [github/github-mcp-server](https://github.com/github/github-mcp-server).
- [microsoft/azure-mcp](https://github.com/microsoft/azure-mcp).
- `035_others/planes-and-mcp.md` §1, §3, §4, §5 — MCP rationale, capability matrix, confused-deputy defence.
- `035_others/threat-model.md` §3 MAS02 — confused-deputy MCP mitigation lives here.

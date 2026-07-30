# Iteration 1 (Read-Only) — SRE Steward (`hello-sre`)

The fourth MeshOps steward: a **read-only** `observe → reason → report` agent that
correlates **three substrates in one reasoning cycle** — Azure Managed Prometheus,
read-only AKS cluster state, and Langfuse traces/eval scores — into an incident
picture. This is the first **AIOps correlation** steward in the portfolio.

> **New to this steward? Start with [`01_use_case.md`](01_use_case.md) §3** — it
> explains why SRE is different from the one-substrate stewards: it joins metrics ×
> cluster state × LLM traces so it can reason about incidents no single peer sees.

## The docs (mirrors the Pipeline and Quality stewards)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | **What the SRE steward does + how it connects the mesh.** The AIOps correlation story, the three substrates, no-write guarantees, acceptance criteria. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | How it's built — settings, `IncidentObservation`, three-tool `build_mcp_tools`, chat server with three async MCP contexts, prompts, chart, RBAC. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | **The hands-on prompt playbook** — exact prompts to paste at the live SRE endpoint, expected answers, and troubleshooting. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy + verify + teardown, including Workload Identity, NSG, Langfuse CSI reattach, and Helm gotchas. |

## Live endpoints (lab)

| Steward | Chat URL | Watches |
|---|---|---|
| SRE (this) | `http://20.118.97.250:8080/` | Prometheus metrics × AKS state × Langfuse traces |
| Pipeline | `http://135.233.240.146:8080/` | MLflow registry — versions & stages |
| Quality | Langfuse-backed endpoint | Langfuse traces + eval scores |
| Inference | `http://104.44.182.236:8080/` | KAITO Workspace — replicas & GPU |

*(LoadBalancer IPs can change if a Service is recreated — re-fetch with
`kubectl -n meshops get svc hello-sre-iter1-chat`.)*

## The one-line mental model

**SRE** is the cross-cutting correlation lens: Prometheus says *what changed*,
AKS says *where it is happening*, and Langfuse says *whether LLM behaviour moved
with it*. The steward produces advice only — no write tool exists in Iteration 1.

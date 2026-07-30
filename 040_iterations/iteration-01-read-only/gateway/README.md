# Iteration 1 (Read-Only) — Gateway Steward (`hello-gateway`)

The fifth MeshOps steward: a **read-only** `observe → reason → report` agent that
watches the platform's **LLM routing and cost-governance plane**. Its substrate is
the in-cluster LiteLLM proxy: named routes, per-route budget caps, and upstream
health.

> **New to this steward? Start with [`01_use_case.md`](01_use_case.md) §3** — it
> explains how Gateway fits into the mesh as the routing/cost lens alongside
> Inference, Pipeline, Quality, and SRE.

## The docs (mirrors the Pipeline, Quality, and SRE stewards)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | **What the Gateway steward does + how it connects the mesh.** The LiteLLM routing-plane story, route/budget/health reads, no-write guarantees, acceptance criteria. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | How it's built — settings, `GatewayObservation`, one-tool `build_mcp_tools`, chat server, prompts, chart, and why there is no read RBAC. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | **The hands-on prompt playbook** — exact prompts to paste at the live Gateway endpoint, expected answers, and troubleshooting. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy + verify + teardown, including Workload Identity, Key Vault, LiteLLM master key, NSG, and Helm gotchas. |

## Live endpoints (lab)

| Steward | Chat URL | Watches |
|---|---|---|
| Gateway (this) | `http://48.192.170.188:8080/` | LiteLLM routes × budget caps × upstream health |
| SRE | `http://20.118.97.250:8080/` | Prometheus metrics × AKS state × Langfuse traces |
| Pipeline | `http://135.233.240.146:8080/` | MLflow registry — versions & stages |
| Quality | Langfuse-backed endpoint | Langfuse traces + eval scores |
| Inference | `http://104.44.182.236:8080/` | KAITO Workspace — replicas & GPU |

*(LoadBalancer IPs can change if a Service is recreated — re-fetch with
`kubectl -n meshops get svc hello-gateway-iter1-chat`.)*

## The one-line mental model

**Gateway** is the routing and cost-governance lens: LiteLLM says *which route is
served*, each route's `max_budget` says *what spend is capped at*, and upstream
health says *whether the lane is usable*. The steward produces advice only — no
write tool exists in Iteration 1.

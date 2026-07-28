# Iteration 1 (Read-Only) — Pipeline Steward (`hello-pipeline`)

The second MeshOps steward: a **read-only** `observe → reason → report` agent that
watches an **MLflow Model Registry** and reasons about model **promotion-readiness**
(UC-03 / MLOps). Same discipline as the Inference steward — zero writes, no HITL — pointed
at a new substrate.

> **New to this steward? Start with [`01_use_case.md`](01_use_case.md) §3** — it
> explains, in plain English, what this steward does and **how it connects to the
> Inference Steward** (the two watch opposite ends of the same model's life).

## The docs (mirrors the Inference steward)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | **What the Pipeline steward does + how it connects to Inference.** The story, the registry substrate, the mesh diagram, acceptance criteria. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | How it's built — module, `mlflow-mcp` shim, prompts, chart, MLflow substrate. Calls out only what differs from the Inference build. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | **The hands-on prompt playbook** — exact prompts to paste, expected answers, and a side-by-side of both stewards live. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy + verify + teardown, including the subnet-NSG gotcha and cost hygiene. |

## Live endpoints (lab)

| Steward | Chat URL | Watches |
|---|---|---|
| Pipeline (this) | `http://135.233.240.146:8080/` | MLflow registry — versions & stages |
| Inference (read-only) | `http://104.44.182.236:8080/` | KAITO Workspace — replicas & GPU |

*(LoadBalancer IPs can change if a Service is recreated — re-fetch with
`kubectl -n meshops get svc hello-pipeline-chat`.)*

## The one-line mental model

**Pipeline** decides *which version* of `phi-4-mini` should be live (the registry
ledger). **Inference** watches *how well the live version is serving* (the GPU
node). The registry's `Production` tag is the baton between them.

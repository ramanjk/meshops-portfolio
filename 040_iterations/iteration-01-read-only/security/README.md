# Iteration 1 (Read-Only) — Security Steward (`hello-security`)

The sixth MeshOps steward: a **read-only** `observe → reason → report` agent that
watches the platform's **input-trust queue**. Its substrate is not Kubernetes or
an infra plane; it is GitHub — the repo's open pull requests, including peer
stewards' HITL proposals on `hitl/*` branches.

> **New to this steward? Start with [`01_use_case.md`](01_use_case.md) §3** — it
> explains how Security fits into the mesh as the vetting lens over the other
> stewards' proposals, catching prompt-injection, confused-deputy, and
> data-poisoning risk before the platform trusts an input.

## The docs (mirrors the Pipeline, Quality, SRE, and Gateway stewards)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | **What the Security steward does + how it connects the mesh.** The GitHub proposal-queue story, threat rubric, no-write guarantees, acceptance criteria. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | How it's built — GitHub read MCP, settings, `SecurityObservation`, agent/chat server, prompts, chart, and why there is no RBAC. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | **The hands-on prompt playbook** — exact prompts to paste at the live Security endpoint, expected answers, and troubleshooting. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy + verify + teardown, including Workload Identity, Key Vault, GitHub token Secret, NSG, and Helm gotchas. |

## Live endpoints (lab)

| Steward | Chat URL | Watches |
|---|---|---|
| Security (this) | `http://172.206.149.75:8080/` | GitHub open PR queue × steward proposal branches × PR bodies/diffs |
| Gateway | `http://48.192.170.188:8080/` | LiteLLM routes × budget caps × upstream health |
| SRE | `http://20.118.97.250:8080/` | Prometheus metrics × AKS state × Langfuse traces |
| Pipeline | `http://135.233.240.146:8080/` | MLflow registry — versions & stages |
| Quality | Langfuse-backed endpoint | Langfuse traces + eval scores |
| Inference | `http://104.44.182.236:8080/` | KAITO Workspace — replicas & GPU |

*(LoadBalancer IPs can change if a Service is recreated — re-fetch with
`kubectl -n meshops get svc hello-security-iter1-chat`.)*

## The one-line mental model

**Security** is the input-trust lens: GitHub says *which proposals and PRs are
about to be trusted*, PR bodies and diffs say *what content would enter the
platform*, and the rubric says *whether it looks like prompt injection,
confused-deputy, or data poisoning*. The steward produces advice only — no write
tool exists in Iteration 1.

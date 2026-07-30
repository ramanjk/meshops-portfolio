# Iteration 2 (Gated Write + HITL) — SRE Steward (`hello-sre`)

The fourth MeshOps steward to graduate to gated write. It keeps the read-only
AIOps correlation loop (Prometheus × AKS × Langfuse) and gains exactly **one**
write-adjacent capability: propose scaling an allow-listed Kubernetes Deployment
replica count. The actual `kubectl scale` happens only after human approval per
[ADR-0011](../../../035_others/decisions/0011-no-autonomous-actuation-hitl.md).

## The docs (mirrors Pipeline and Quality)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | Why Deployment scale is the SRE write, why KAITO Workspace count is not, and the three defence layers. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | `ScaleProposal`, `KubectlScaleApplier`, `propose_scale`, shared HITL spine, Helm/RBAC wiring. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | Live prompt/PR/approve test playbook against `http://20.94.174.157:8080/`. |
| [`04_test_cases_automated.md`](04_test_cases_automated.md) | Unit tests for SRE settings/schema/prompt/write plus shared HITL gate tests. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy `hello-sre-iter2` with `github_pr` approval, demo workload, NSG, verification. |

## Live endpoint (lab)

| Steward | Chat URL | Write path |
|---|---|---|
| SRE gated writer | `http://20.94.174.157:8080/` | `propose_scale` → GitHub PR → merge approves → `kubectl scale` |

## The one-line mental model

**SRE is the first correlation/AIOps writer:** it correlates incident signals, then
may propose one reversible remediation — scaling `Deployment/demo-web` in
`meshops-workloads` within `0..5` replicas — but only a human-approved PR makes it real.

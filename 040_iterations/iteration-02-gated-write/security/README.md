# Iteration 2 (Gated Write + HITL) — Security Steward (`hello-security`)

The sixth MeshOps steward to graduate to gated write, and the first SecOps
writer. It keeps the read-only input-trust loop (GitHub open PRs × `hitl/*`
steward proposal branches × PR bodies/diffs) and gains exactly **one**
write-adjacent capability: propose quarantining a suspicious PR by applying an
allow-listed GitHub label. The actual label add happens only after human approval
per [ADR-0011](../../../035_others/decisions/0011-no-autonomous-actuation-hitl.md).

## The docs (mirrors Pipeline, Quality, SRE, and Gateway)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | Why PR quarantine is the Security write, why it targets GitHub not the cluster, and the three defence layers. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | `QuarantineProposal`, `GitHubLabelApplier`, `propose_quarantine`, shared HITL spine, Helm/no-RBAC wiring. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | Live prompt/approve/deny/RBAC-proof playbook against `http://172.202.188.183:8080/`. |
| [`04_test_cases_automated.md`](04_test_cases_automated.md) | Unit tests for Security settings/schema/prompt/write plus shared HITL gate guarantees. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy `hello-security-iter2` with chat approval, quarantine label allowlist, NSG, verification. |

## Live endpoint (lab)

| Steward | Chat URL | Write path |
|---|---|---|
| Security gated writer | `http://172.202.188.183:8080/` | `propose_quarantine` → chat approval → GitHub label + audit comment |

## The one-line mental model

**Security is the input-trust writer:** it reads the GitHub proposal queue and may
propose one bounded action — add `quarantined` or `security-hold` to a suspicious
open PR — but only a human-approved gate makes it real. It has no Kubernetes
writer RBAC at all.

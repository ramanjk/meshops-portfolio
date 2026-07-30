# Iteration 2 (Gated Write + HITL) — Gateway Steward (`hello-gateway`)

The fifth MeshOps steward to graduate to gated write. It keeps the read-only
routing/cost loop (LiteLLM routes × budget caps × upstream health) and gains
exactly **one** write-adjacent capability: propose changing an allow-listed
LiteLLM route's per-route `max_budget`. The actual ConfigMap patch + proxy
rollout happens only after human approval per
[ADR-0011](../../../035_others/decisions/0011-no-autonomous-actuation-hitl.md).

## The docs (mirrors Pipeline, Quality, and SRE)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | Why per-route budget cap is the Gateway write, why route/fallback/model changes are not, and the three defence layers. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | `BudgetProposal`, `LiteLLMBudgetApplier`, `propose_budget`, shared HITL spine, Helm/RBAC wiring. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | Live prompt/PR/approve/deny test playbook against `http://20.188.72.89:8080/`. |
| [`04_test_cases_automated.md`](04_test_cases_automated.md) | Unit tests for Gateway settings/schema/prompt/write plus shared HITL gate tests. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy `hello-gateway-iter2` with `github_pr` approval, LiteLLM budget bounds, NSG, verification. |

## Live endpoint (lab)

| Steward | Chat URL | Write path |
|---|---|---|
| Gateway gated writer | `http://20.188.72.89:8080/` | `propose_budget` → GitHub PR → merge approves → patch LiteLLM ConfigMap + rollout restart |

## The one-line mental model

**Gateway is the routing/cost-governance writer:** it reads LiteLLM routes and
health, then may propose one reversible policy change — a route's `max_budget`
within `0..200` for `chat-premium` or `chat-economy` — but only a
human-approved PR makes it real.

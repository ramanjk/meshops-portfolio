# Iteration-03 — Quality Steward (`hello-quality`)

The third MeshOps steward: a **read-only** `observe → reason → report` agent that
watches a **Langfuse project** (LLM **traces** + **evaluation scores**) and reasons
about model **output quality and drift** (UC / LLMOps-quality, agent-catalog §5).
Same discipline as iterations 01–02 — zero writes, no HITL — pointed at a new
substrate that is, uniquely, **the output of the whole mesh**.

> **Status:** built and unit/helm-tested **locally** (38/38 tests pass; `helm lint`/
> `template` clean). **Not yet deployed** — the lab is cost-stopped. Deploy with
> [`05_deployment_guide.md`](05_deployment_guide.md), then run
> [`03_test_cases_manual.md`](03_test_cases_manual.md) as the acceptance script.

> **New to this steward? Start with [`01_use_case.md`](01_use_case.md) §3** — it
> explains, in plain English, what this steward does and **how it connects to the
> Inference *and* Pipeline Stewards** (it's the mesh's quality lens, and the eval
> gate before a promotion).

## The docs (mirrors iterations 01–02)

| Doc | Read it for |
|---|---|
| [`01_use_case.md`](01_use_case.md) | **What the Quality steward does + how it connects to the other two.** The story, the Langfuse substrate (traces + scores), the mesh diagram, the three no-write guarantees, acceptance criteria. |
| [`02_implementation_guide.md`](02_implementation_guide.md) | How it's built — module, `langfuse-mcp` shim, `QualityObservation` schema, prompts, dedicated chart. Calls out only what differs from iter-01/02. |
| [`03_test_cases_manual.md`](03_test_cases_manual.md) | **The hands-on prompt playbook** — exact prompts to paste, expected answers, drift reasoning, no-write PR decline, and the "mesh watching itself" demo. |
| [`05_deployment_guide.md`](05_deployment_guide.md) | Deploy + verify + teardown, including WI federation, the subnet-NSG gotcha, seeding eval scores, and cost hygiene. |

## Live endpoints (lab)

| Steward | Chat URL | Watches |
|---|---|---|
| Quality (this) | `http://<TBD>:8080/` — assigned at deploy | Langfuse — traces & eval scores |
| Pipeline (iter-02) | `http://<TBD>:8080/` — new IP on re-deploy | MLflow registry — versions & stages |
| Inference (iter-01) | `http://<TBD>:8080/` — new IP on re-deploy | KAITO Workspace — replicas & GPU |

*(All IPs are TBD: the old ones were freed at shutdown. After deploy, re-fetch with
`kubectl -n meshops get svc hello-quality-chat -o jsonpath='{.status.loadBalancer.ingress[0].ip}'`.)*

## The one-line mental model

**Inference** watches *how well the live model serves* (the GPU node).
**Pipeline** decides *which version* should be live (the registry ledger).
**Quality** judges *whether the output is any good and whether it's drifting*
(the Langfuse traces + eval scores) — and because every steward emits its traces
to Langfuse, Quality is the one steward whose substrate is **the mesh's own output**.

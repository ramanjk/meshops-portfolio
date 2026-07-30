# Prompt CHANGELOG

## 1.7.0
- Added the **Gateway Steward** (`hello-gateway`) persona trio —
  `gateway-steward.system.md`, `gateway-steward.chat.md`, and
  `gateway-steward.gated-write.chat.md`. This is the fifth steward and the first
  **LLM routing / cost governance** steward. Its substrate is the platform's
  **LiteLLM proxy**: named **routes** (model groups) over the platform's models,
  each with a per-route **budget cap** (`max_budget`) and an upstream deployment.
  - Iteration 1 (read-only): observe → assess → report a routing-plane posture
    (routes, per-route budget caps, upstream health) via the in-repo
    `litellm-mcp` shim (`list_routes`, `route_health`). Same three no-write
    guarantees and non-negotiable identity anchoring as the other stewards;
    `requires_hitl` forced false; `proposed_adjustment` explicitly scoped as
    *advice*, not an action.
  - Iteration 2 (gated write + HITL): `propose_budget` — change a route's
    **per-route budget cap**, bounded to an allow-listed route set and a budget
    range, actuated by deterministic code (patch the LiteLLM config ConfigMap +
    roll the proxy) under a namespaced writer Role — never the LLM. Reuses the
    shared `src/stewards/hitl/` propose→approve→apply→audit spine and pluggable
    chat/github_pr channels (ADR-0011: *no autonomous actuation*). Loaded only
    when `write_enabled=true`; otherwise the read-only `gateway-steward.chat.md`
    persona is used unchanged.

## 1.6.0
- Added the **SRE Steward** (`hello-sre`) persona trio —
  `sre-steward.system.md`, `sre-steward.chat.md`, and
  `sre-steward.gated-write.chat.md`. This is the fourth steward and the first
  **AIOps / correlation** steward: unlike its peers (each scoped to one
  substrate), it joins **three read substrates** — Azure Managed Prometheus
  (metrics), the AKS cluster itself (workloads/events/nodes via read-only
  `aks-mcp`), and the Langfuse project (LLM traces + eval scores) — into a
  single incident timeline + root-cause hypothesis + advice-only remediation.
  - Iteration 1 (read-only): observe → correlate → report. Same three no-write
    guarantees and non-negotiable identity anchoring as the other stewards;
    `requires_hitl` forced false; `proposed_remediation` explicitly scoped as
    *advice*, not an action.
  - Iteration 2 (gated write + HITL): `propose_scale` — change a Kubernetes
    **Deployment's replica count** (the scaler-tuning remediation), bounded to
    an allow-listed namespace/deployment set and replica range, actuated by
    deterministic `kubectl scale` under a namespaced writer Role — never the
    LLM. Reuses the shared `src/stewards/hitl/` propose→approve→apply→audit
    spine and pluggable chat/github_pr channels (ADR-0011: *no autonomous
    actuation*). Loaded only when `write_enabled=true`; otherwise the read-only
    `sre-steward.chat.md` persona is used unchanged.

## 1.5.0
- Added `pipeline-steward.gated-write.chat.md` and
  `quality-steward.gated-write.chat.md` — the **Iteration 2 (gated write +
  HITL)** personas for the Pipeline and Quality Stewards, extending the depth
  ladder that started with the Inference Steward. Reads stay ungated; each
  steward may now **propose exactly one kind of mutation** but never executes
  it — every write waits for a human's approval at the gate (ADR-0011: *no
  autonomous actuation*):
  - Pipeline → `propose_promotion`: an MLflow model-version **stage transition**
    (e.g. promote the Staging candidate to Production), bounded to the single
    registered model `phi-4-mini-meshops`.
  - Quality → `propose_annotation`: attach a numeric **evaluation score** to a
    specific Langfuse trace (a human-review annotation).
  Loaded only when `write_enabled=true`; otherwise the read-only
  `*-steward.chat.md` personas are used unchanged. The propose→approve→apply→
  audit spine and pluggable chat/github_pr channels are shared across all three
  stewards via the new `src/stewards/hitl/` package.

## 1.4.0
- Added `inference-steward.gated-write.chat.md` — the **Iteration 2 (gated
  write + HITL)** persona for the Inference Steward. Reads stay ungated; the
  steward may now **propose** any mutation via the `propose_write` tool but
  never executes it — every write waits for a human's approval at the gate
  (ADR-0011: *no autonomous actuation*). Loaded only when `write_enabled=true`;
  otherwise the read-only `inference-steward.chat.md` persona is used unchanged.

## 1.3.0
- Added `quality-steward.system.md` and `quality-steward.chat.md` for the
  **Quality Steward** (`hello-quality`). Read-only (Iteration 1) LLMOps-quality
  persona that observes a Langfuse project (LLM traces + evaluation scores) and
  reasons about eval health and drift. Same three no-write guarantees and
  non-negotiable identity anchoring as the Inference and Pipeline Stewards;
  `requires_hitl` forced false and `drift_suspected` explicitly scoped as a
  read-only signal (not an action).

## 1.2.0
- Added `pipeline-steward.system.md` and `pipeline-steward.chat.md` for the
  **Pipeline Steward** (`hello-pipeline`). Read-only (Iteration 1) MLOps persona
  that observes an MLflow Model Registry and reasons about promotion-readiness
  (`None → Staging → Production → Archived`). Same three no-write guarantees and
  non-negotiable identity anchoring as the Inference Steward; `requires_hitl`
  forced false.

## 1.1.0
- `inference-steward.chat.md`: strengthened identity anchoring for the small
  chat model (phi-4-mini). Added a non-negotiable **Identity** section so the
  steward always self-identifies as the "Inference Steward" and never as a
  generic AI assistant / language model, including a canonical self-intro line
  and a rule for "what model are you" questions.

## 1.0.0
- Initial system prompt for `hello-inference` (the Inference Steward, Iteration 1 read-only).
- Read-only stance; no `proposed_actions`; `requires_hitl` forced false.

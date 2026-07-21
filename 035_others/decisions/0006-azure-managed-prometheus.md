# ADR-0006: Use Azure Managed Prometheus + Azure Managed Grafana for cluster and agent metrics

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

MeshOps needs a Prometheus-compatible metrics backend for:

- Standard cluster metrics (node CPU, GPU utilisation, pod restarts, KAITO Workspace status).
- Agent-emitted GenAI metrics — `gen_ai.client.operation.duration`, `gen_ai.client.token.usage`, `agent_framework.function.invocation.duration` — exported by Microsoft Agent Framework's OTel Prometheus exporter on each steward pod's `:9464`.
- Future eval drift signals (P1) — Promptfoo / Ragas write pass/fail counts and faithfulness scalars as Prometheus metrics for the Quality Steward to consume.

Three concrete options:

- **Azure Managed Prometheus + Managed Grafana** (Microsoft-managed).
- **Self-hosted `kube-prometheus-stack`** Helm chart in the cluster.
- **A third-party SaaS** (Datadog, New Relic, etc.).

`035_others/cost-and-deployment.md` §2 hints at "Prom + Grafana free OSS" but the line is not load-bearing. The Azure-first principle (ADR-0003) plus Ram's MS quota plus the desire to *avoid* operating Prom HA at portfolio scale points strongly to managed.

Microsoft Managed Prometheus also supports the `PodMonitor` and `ServiceMonitor` CRDs (`azmonitoring.coreos.com/v1`) — i.e., the steward pods scrape themselves through a CRD that looks just like upstream Prometheus Operator. No code-level lock-in.

## Decision

MeshOps adopts **Azure Managed Prometheus** as the metrics backend and **Azure Managed Grafana** as the dashboard surface. Each is provisioned per cluster via Terraform (`infra/terraform/monitoring.tf`). Custom scrape configs live in the cluster as `PodMonitor` / `ServiceMonitor` CRDs (`azmonitoring.coreos.com/v1`). Each steward chart ships its own `PodMonitor`.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) Azure Managed Prometheus + Managed Grafana (chosen)** | Microsoft-native; PodMonitor CRD works as expected; covered by MS quota for Ram; no HA to operate | Slight learning curve for the `azmonitoring.coreos.com/v1` group (different from `monitoring.coreos.com/v1`); cost above free tier on heavy use | **Chosen** |
| (b) Self-hosted `kube-prometheus-stack` | Full upstream Prom; vendor-neutral | We operate Prom HA + retention + scaling ourselves; doesn't leverage MS quota | Rejected — wrong axis for portfolio focus |
| (c) Datadog / New Relic / etc. | Strong UX, lots of integrations | Non-Microsoft service; ADR-0003 says no | Rejected — Azure-first principle |
| (d) Skip Prometheus, only use Langfuse + App Insights | Less to operate | Loses cluster metrics (GPU, KAITO Workspace) | Rejected — we need both cluster + LLM signals |

## Consequences

**Positive:**

- One `PodMonitor` per steward chart is enough to onboard metrics.
- Managed Grafana ships with Entra ID integration out of the box; no separate identity story.
- Cluster metrics, KAITO metrics, and agent GenAI metrics all live in one workspace.
- Postpones the long-term-retention question to a later ADR (Managed Prom retention defaults are sufficient for v1).

**Negative / accepted trade-offs:**

- `azmonitoring.coreos.com/v1` vs upstream `monitoring.coreos.com/v1` is a real distinction — copy/paste from a generic Prom-Operator example does not work without tweak. Documented in `06-deployment.md`.
- A future migration off Azure Managed Prometheus would require re-creating dashboards in a vendor-neutral exporter (small, but real).

**Things we'll need to revisit:**

- Recording / alerting rules for SLOs land with the SRE Steward in P2.
- Long-term retention (cold store) for compliance / postmortem replay is a P3+ question.

## References

- [Azure Managed Prometheus — PodMonitor / ServiceMonitor CRDs](https://learn.microsoft.com/en-us/azure/azure-monitor/containers/prometheus-metrics-scrape-crd) — `azmonitoring.coreos.com/v1`.
- [Azure Monitor — managed Prometheus default scrape](https://learn.microsoft.com/en-us/azure/azure-monitor/containers/prometheus-metrics-scrape-default).
- [Azure Managed Grafana](https://learn.microsoft.com/en-us/azure/managed-grafana/).
- [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — `gen_ai.client.*` metric names.
- `035_others/architecture.md` §7 — Prom + Grafana row.
- `035_others/eval-and-llmops.md` §5 — metric → tool → threshold reference table.

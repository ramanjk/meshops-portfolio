# ADR-0005: Use Langfuse (self-hosted) as the LLM observability surface, via OpenTelemetry GenAI conventions

- **Status:** Proposed
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

Stewards generate two flavours of telemetry:

- **Cluster / pod / system metrics** — CPU, memory, request rates, GPU utilisation. Standard Prometheus territory. (Covered by ADR-0006.)
- **LLM-specific traces and metrics** — prompts, responses, token usage per call, per-tool spans, latency per `chat` / `execute_tool`, agent-loop traces with parent/child spans. Standard Prometheus + Grafana does not give you these natively.

Microsoft Agent Framework 1.0 emits LLM-specific telemetry via OpenTelemetry following the **GenAI Semantic Conventions** (`gen_ai.client.*`, `invoke_agent <name>`, `chat <model>`, `execute_tool <function>`). The recommended Python entry point is `agent_framework.observability.configure_otel_providers()` (Microsoft Learn, 2026-04-01). That entry point reads `OTEL_EXPORTER_OTLP_ENDPOINT` and ships spans to any OTLP-compatible backend.

That gives MeshOps the freedom to pick the LLM observability product. Candidates:

- **Azure Application Insights / Azure Monitor** — Microsoft-native; well integrated with Foundry tracing.
- **Langfuse** — open-source LLM observability product. Self-hostable on K8s via Helm. Strong UI for traces + token cost + per-call drill-down. The Microsoft Agent Framework docs explicitly call out a Langfuse integration path.
- **Arize Phoenix / LangSmith / Helicone** — also strong, but each adds a non-Microsoft service.

Given the Microsoft-first stack (ADR-0003), Application Insights might seem the natural pick. But Application Insights' LLM-trace UX is still catching up to the dedicated LLM observability products in 2026, and the Microsoft Agent Framework + Foundry docs themselves point users at Langfuse as a parallel option. The mesh narrative benefits from a dedicated LLM observability surface that hiring managers immediately recognise as LLMOps-native.

## Decision

MeshOps uses **Langfuse, self-hosted on AKS via the community Helm chart**, as its LLM observability surface. Stewards emit OpenTelemetry GenAI traces via `agent_framework.observability.configure_otel_providers()` to the in-cluster Langfuse OTLP endpoint.

**Why self-host (not Langfuse Cloud) in iteration-01 onward:** keeping all trace data inside the lab AKS cluster simplifies the confidentiality story (`CLAUDE.md` §Confidentiality — multi-agent telemetry incidentally captures cluster state).

`ENABLE_SENSITIVE_DATA` remains `false` in v1 to avoid prompt/response payloads leaving the cluster's trust boundary even by accident.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) Langfuse self-hosted on AKS (chosen)** | Best-in-class LLM trace UX; data stays in lab cluster; OSS; MAF integration documented | Adds Postgres + Clickhouse + Redis dependencies in-cluster | **Chosen** |
| (b) Langfuse Cloud | Zero ops cost | Trace data leaves the trust boundary; tighter confidentiality review per `CLAUDE.md` | Rejected for v1 — confidentiality margin |
| (c) Azure Application Insights / Azure Monitor only | Microsoft-native; integrates with Foundry tracing | LLM-trace UX less mature in 2026; less recognisable hiring keyword | Rejected — keyword + UX trade-off |
| (d) Arize Phoenix / LangSmith | Strong UX | Non-Microsoft service; adds account dependency | Rejected — Azure-first principle |
| (e) Both Langfuse + App Insights ("belt and suspenders") | Most coverage | 2x ops cost; duplicate retention; minor split-brain risk | Deferred — add App Insights for *agent* traces (not steward traces) once the Foundry-hosted Quality Steward lands in P1 |

## Consequences

**Positive:**

- LLM trace tree (`inference.steward.cycle` → `invoke_agent` → tool calls → `chat`) renders natively in a tool reviewers will recognise.
- Token usage + cost surfaces are first-class in the UI.
- OTLP-based pipeline means we can fan out to App Insights later without re-instrumenting code.

**Negative / accepted trade-offs:**

- Three additional dependencies in-cluster (Postgres, Clickhouse, Redis) for v1.
- Trace retention story for v1 is "30 days, then drop" — no long-term cold store yet.

**Things we'll need to revisit:**

- Whether to add App Insights *alongside* Langfuse for the Foundry-hosted Quality Steward in P1.
- Whether to externalise Langfuse's Postgres + Clickhouse to managed services in P2 (Azure Database for PostgreSQL Flexible Server + ?) once trace volume justifies it.
- Whether to flip `ENABLE_SENSITIVE_DATA` to `true` in a *named* debug environment under HITL gate — currently no.

## References

- [Microsoft Learn — Agent Framework Observability (Python)](https://learn.microsoft.com/en-us/agent-framework/agents/observability) — `configure_otel_providers`.
- [Langfuse — Microsoft Agent Framework integration](https://langfuse.com/integrations/frameworks/microsoft-agent-framework).
- [Langfuse — Kubernetes Helm self-host](https://langfuse.com/self-hosting/deployment/kubernetes-helm).
- [OpenTelemetry GenAI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — `gen_ai.*` names.
- `035_others/eval-and-llmops.md` §2 — drift signals consumed by the Quality Steward via Langfuse.
- `035_others/cost-and-deployment.md` §2 — Langfuse self-host fits inside the cluster footprint.
- `CLAUDE.md` §Confidentiality — trace-export review rule.

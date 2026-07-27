# MeshOps — Prompting Strategy (how this project was built with an AI agent)

*A presentation-ready answer to: "What prompt did you use for this project?"*

## The honest one-liner

> I didn't one-shot it. I gave the agent a **strong context/role prompt** up
> front, then drove it **iteration by iteration** with small, verifiable goals —
> build the read-only slice first, prove it live, then expand. The AI wrote the
> code and manifests; **I made the architecture and safety decisions.**

The value wasn't a clever one-liner — it was knowing *what* to ask for, *in what
order*, and *how to verify it*. Same skill as leading a strong engineer.

---

## 1. The master kickoff prompt (the "constitution")

The big context-setting prompt, given once up front:

```
You are helping me build "MeshOps" — a portfolio project: a mesh of six
autonomous "steward" agents that operate an AKS-based LLM/SLM platform, one
per Ops domain (Inference/LLMOps, Pipeline/MLOps, Quality, Gateway, SRE, Sec).

Substrate & stack (fixed):
- Azure Kubernetes Service (lab, single sub), Workload Identity (no stored keys)
- Microsoft Agent Framework (MAF, Python) for each agent
- MCP servers as the ONLY way agents touch the world (tools = capability boundary)
- Azure OpenAI (gpt-4.1) for reasoning
- Langfuse (self-hosted) + OpenTelemetry + Managed Prometheus for observability
- KAITO Workspaces for model serving; MLflow Model Registry for the pipeline

Non-negotiable engineering principles:
1. Build in thin vertical slices. Each iteration = ONE steward, and only the
   read-only "observe -> reason -> report" half first. Defer propose/act/HITL.
2. Safety is defence-in-depth. A read-only steward must be unable to write via
   THREE independent layers: (a) tools expose no write verbs, (b) the persona
   forbids writes, (c) the output schema cannot express a write.
3. Everything runs least-privilege: Workload Identity, RBAC scoped to reads,
   secrets never in code or logs.
4. Prove it end-to-end on real infra before calling it done, and leave a trace.
5. Ship a working steward FIRST, then a concise guide. Full docs later.

Work with me iteratively. Before major decisions, ask me. Track progress in a
plan. Keep changes surgical and validate (tests, lint, live smoke test).
```

---

## 2. The per-steward build prompt (reused each iteration)

The template fired for each steward — swap the substrate:

```
Build steward #N: the <NAME> Steward (<Ops domain>), as a NEW read-only agent
that mirrors the discipline of the Inference steward.

- Substrate it observes: <e.g. an MLflow Model Registry>
- The ONE thing it reasons about: <e.g. is the Staging candidate promotion-ready?>
- Tool: a read-only MCP shim exposing ONLY read verbs against <substrate API>
- Output: a narrow Pydantic schema with a no-write validator (requires_hitl=False)
- Persona: non-negotiable identity (always "<NAME> Steward", never a generic
  assistant/model), forbids writes, declines change requests
- Reuse verbatim: the agent loop, Azure OpenAI client, Langfuse/OTel wiring,
  the FastAPI chat server, the empty-prompt fallback, the Helm patterns

Then: deploy the substrate, seed realistic data, build the image, wire Workload
Identity, deploy via a dedicated Helm chart, and verify E2E live (identity,
real read, no-write refusal, a Langfuse trace). Finish with a concise guide.
```

---

## 3. The follow-up prompts that actually steered it

The real work was short, corrective, verifiable turns. These show engineering
judgment — the part that matters:

- *"Instead of port-forward, expose the service with a LoadBalancer and use
  ingress if needed."* → forced real network / NSG problem-solving.
- *"The steward says it can't list namespaces, but per its persona it should have
  all read capabilities."* → drove the least-privilege RBAC design.
- *"Cross-check everything, make sure it's pushed, then continue to the next
  steward."* → verification discipline.
- *"I understand the Inference steward but not how the two connect — make a clear
  doc and help me test prompts."* → docs + live validation.
- *"Overnight shutdown."* → cost hygiene.

---

## 4. The talking track (if they push "so the AI did everything?")

> The AI was the implementer; I was the architect and the reviewer. **My prompts
> encoded the decisions** — the slice boundaries, the three-layer no-write safety
> model, least-privilege identity, the observe-first staging. The value wasn't a
> clever one-liner; it was **knowing what to ask for, in what order, and how to
> verify it.** Same skill as leading a strong engineer.

---

## 5. Why this prompting approach works (the meta-point)

| Principle | What it prevented |
|---|---|
| Thin read-only slices first | Big-bang agents that can break prod on day one |
| Three-layer no-write safety in the prompt | Trusting a single prompt line to keep an LLM safe |
| "Prove it live before done" | "Works on paper" demos that fall over in front of the team |
| "Ship working steward, then docs" | Doc-first paralysis; kept momentum |
| Iterative + "ask before big decisions" | The AI guessing architecture I hadn't decided |

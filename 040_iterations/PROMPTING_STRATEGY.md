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

## 0. Where the idea came from (before any prompt)

The concept was **mine, from real pain — not from a prompt.** The project
proposal (`020_project_proposal/proposal.md`) opens with a "2 a.m. story": an
on-call engineer paged while a production LLM platform on AKS misbehaves —
latency doubling, a fine-tune queued for promotion, a RAG corpus just refreshed,
the GPU nodepool near saturation. **Four problems, four specialties
(LLMOps / MLOps / AIOps / SecOps), one tired human.**

The insight that turned that pain into MeshOps was the **service-mesh move**:
just as service mesh lifted retries/routing/security out of every microservice
into a shared plane, MeshOps lifts each *operational* concern into its own small
AI **steward** — with one safety line: **autonomy lives at the *proposal* layer,
never at *actuation*** (a human always approves).

It was also **career-driven**: 11 years of AKS depth + Kubestronaut meant the
cluster wasn't the new skill — the *agentic AI + LLMOps craft on top* was. The
six stewards were deliberately chosen so four lean on what I already know and two
(Quality, Security) stretch me into new territory.

**Was a prompt used for the ideation?** The concept was mine; the AI helped
*shape and pressure-test* it into a structured proposal. This is the kind of
framing prompt that reflects that conversation:

```
I'm a senior Kubernetes/AKS engineer (11 yrs, Kubestronaut) trying to move into
an AI Platform / MLOps / LLMOps role. I want a portfolio project that:
- shows off what I already know cold (AKS, GPU nodepools, GitOps, Prometheus)
- forces me to learn the NEW stuff a hiring panel screens for (agents, MCP,
  LLMOps eval, LLM security)
- is genuinely agentic (a plan->act->observe loop with real tools), not a chatbot
- is safe enough to be real (nothing touches prod without a human approval).

Help me pressure-test this idea: operating an LLM platform on AKS is really four
jobs braided together (LLMOps, MLOps, AIOps, SecOps). What if I apply the
service-mesh pattern to OPERATIONS — a mesh of small specialist "steward" agents,
one per concern, each proposing fixes behind a human-in-the-loop gate?

Challenge the concept, name the right set of stewards, map each to a skill I
have vs. a skill I need to build, and tell me what would make it credible to a
Microsoft AI Platform hiring panel.
```

**Talking track ("did the AI come up with the idea?"):**

> No — the idea came from the operational pain I live every week. I used the AI to
> *sharpen* it: naming the right six stewards, applying the service-mesh analogy
> cleanly, and pressure-testing the safety model. The concept and the career
> strategy were mine; the AI was a thinking partner that helped me structure it
> into a proposal and then build it.

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

# MeshOps — LinkedIn Post Series

Text-only posts for promoting the MeshOps project on LinkedIn.

---

## Post #1 — Project Intro

Running an AI platform isn't one job. It's four — braided together for one tired
human at 2 a.m.

Every on-call night on an LLM platform looks the same: latency doubling, a
fine-tune queued for promotion, the RAG corpus just changed, the GPU pool maxing
out. That's LLMOps, MLOps, AIOps, and SecOps all at once — one engineer, four hats.

Service mesh solved a version of this for microservices: it lifted routing,
retries, and security out of every app into a shared plane.

So I asked — what if you apply that same pattern to *operations*?

That's MeshOps: a mesh of small, specialist AI "steward" agents, one per
operational concern. Each steward observes live cluster state, reasons over it,
and proposes a fix.

The rule I'm proudest of: stewards propose, humans dispose. They're read-only by
design — nothing touches production without a human approving. Autonomy stops at
the *proposal* layer.

Built on AKS + Azure OpenAI + MCP tools + Workload Identity. After 11 years in
Kubernetes (Kubestronaut), this is my deliberate stretch into agentic AI and
LLMOps.

Two stewards are already live. I'll introduce the first one in my next post.

#Kubernetes #AKS #LLMOps #MLOps #AIAgents #Azure #MCP #PlatformEngineering

---

## Post #2 — Steward #1: The Inference Steward

Meet the first MeshOps steward: the Inference Steward.

In my last post I introduced MeshOps — a mesh of read-only AI agents that operate
an LLM platform on AKS, one per ops concern. Here's steward #1.

What it does: the Inference Steward watches the *serving* side of the platform —
the live model behind a KAITO Workspace on AKS. Is the workspace healthy? How many
replicas? Is the model actually answering? It reasons over that live state and
reports what it sees.

What makes it interesting:
- It's a real agent — an observe -> reason -> report loop with tools over MCP,
  not a chatbot.
- It's grounded in live cluster state, not a canned demo.
- It's read-only, enforced three ways: the tools only expose read verbs, the
  persona declines any write, and the output schema hard-fails on a change
  request. Ask it to "promote a model" and it politely refuses.

Why that matters: an AI agent you can trust in production is one that *can't*
touch it without you. Safety isn't a disclaimer — it's built into the architecture.

Next up: the Pipeline Steward, and how the two connect through the model registry.

#LLMOps #AIAgents #Kubernetes #AKS #Azure #MCP #MLOps #PlatformEngineering

---

## Post #3 — Steward #2: The Pipeline Steward + how the two connect (draft)

Steward #2 is live: the Pipeline Steward — and this is where MeshOps becomes a
*mesh*.

The Pipeline Steward watches the MLOps side: the MLflow Model Registry. Which
model version is in Staging? Which is Production? Which got Archived? It reads the
registry over its API and reasons about promotion state — read-only, same
three-way safety as steward #1.

Here's the part I love — how the two stewards connect:
- Pipeline Steward (upstream) watches the registry: "version 2 is Production."
- Inference Steward (downstream) watches serving: "the workspace is healthy, 1
  replica answering."
- The registry's "Production" tag is the baton passed between them.

I proved it live, side by side: asked both the same day — Pipeline said
"Production = v2," Inference said "workspace healthy, serving." Two independent
agents, one coherent picture of the platform. That's the mesh.

Four more stewards to go (Quality, Security, and more). Follow along.

#LLMOps #MLOps #AIAgents #Kubernetes #AKS #Azure #MCP #PlatformEngineering

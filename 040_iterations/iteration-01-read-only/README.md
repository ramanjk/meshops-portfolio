# Iteration 1 — Read-Only Foundation (across stewards)

*This folder is a **maturity phase**, not a steward. It collects the read-only build of every steward we've stood up so far. Read this first — it defines the two axes the whole project moves along, and where each steward sits today.*

## Two axes: steward (breadth) vs iteration (depth)

MeshOps grows along **two independent axes**, and it's important not to conflate them:

- **Steward (breadth) — *which* Ops domain.** Inference, Pipeline, Quality, SRE, Gateway, Security (see `035_others/agent-catalog.md`). Each is a separate agent watching a separate substrate.
- **Iteration (depth) — *how much power* an agent has.** This is the **capability-maturity** ladder, and it is the same ladder for every steward:

| Iteration | Capability | What the agent may do |
|---|---|---|
| **Iteration 1 — read-only** | `observe → reason → report` | Read its substrate, reason, explain. **Zero writes**, enforced three ways. |
| **Iteration 2 — gated write (HITL)** | `observe → reason → propose → HUMAN APPROVES → act` | Propose a change and, only after a human approves at the HITL gate, execute it. (Per ADR-0011: *no autonomous actuation*.) |
| **Iteration 3+ — broader / auto-approved** | wider action scope | Expand the action set, or auto-approve provably low-risk actions. |

> **"Iteration" ≠ "steward."** An earlier version of the plan said *"each iteration = one steward,"* which quietly conflated the two axes and deferred write/HITL forever. It doesn't. Iteration = maturity level; steward = domain. This phase folder is the **read-only row** of the matrix below.

## The matrix — where we are today

| Steward ↓ / Iteration → | **1 · read-only** | **2 · gated write (HITL)** | **3+ · broader** |
|---|---|---|---|
| **Inference** | ✅ [`inference/`](inference/) | 🚧 [gated-write](../iteration-02-gated-write/inference/) | ⬜ |
| **Pipeline** | ✅ [`pipeline/`](pipeline/) | ⬜ (natural first writer: propose a registry promotion) | ⬜ |
| **Quality** | ✅ [`quality/`](quality/) | ⬜ (propose a prompt-version PR) | ⬜ |
| **SRE** | ⬜ | ⬜ | ⬜ |
| **Gateway** | ⬜ | ⬜ | ⬜ |
| **Security** | ⬜ | ⬜ | ⬜ |

**Iteration 1 is complete for three stewards.** The next step is a *depth* move, not a fourth read-only clone: take one steward (Pipeline is the natural choice — its "propose a promotion" is the cleanest first gated write) into **Iteration 2**, in `../iteration-02-gated-write/` (to be created).

## The three read-only builds

Each subfolder is one steward's Iteration-1 deliverable bundle (same five-doc shape):

| Steward | Substrate it reads | Read-only question it answers |
|---|---|---|
| [**Inference**](inference/) | KAITO Workspace (replicas, GPU) | *Is the deployed model serving healthily right now?* |
| [**Pipeline**](pipeline/) | MLflow Model Registry (versions, stages) | *Which version should be deployed, and is the next candidate ready?* |
| [**Quality**](quality/) | Langfuse project (traces + eval scores) | *Is the model's output any good, and is it drifting?* |

## The load-bearing invariant of Iteration 1

Every steward in this phase is **read-only, enforced three independent ways** (defence-in-depth):

1. **Tools** expose only read verbs (the MCP shims have no write functions).
2. **Persona** forbids writes and declines change requests.
3. **Schema** cannot express a write, and its `requires_hitl` validator hard-fails on `True`.

`requires_hitl` and the propose/act fields are deliberately *absent* here — they are the language of **Iteration 2**, and adding them is precisely what the depth move introduces (behind the HITL gate).

## Cross-cutting assets (one level up, in `040_iterations/`)

- [`PROMPTING_STRATEGY.md`](../PROMPTING_STRATEGY.md) — how this was driven prompt-by-prompt (now describes the maturity ladder).
- [`LINKEDIN_POSTS.md`](../LINKEDIN_POSTS.md) + [`assets/`](../assets/) — portfolio promotion (architecture diagram, posts).

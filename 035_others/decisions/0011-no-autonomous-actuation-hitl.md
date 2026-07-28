# ADR-0011: No autonomous actuation — every write action passes a human-in-the-loop (HITL) gate

- **Status:** Accepted
- **Decider(s):** Kuruva Ramanjaneyulu (Ram)

## Context

Iteration 1 shipped every steward as strictly **read-only** (`observe → reason → report`), with writes blocked three ways (MCP `--access-level readonly`, prompts that decline, and a schema whose validator raises on any write intent). That is safe but inert: a steward that can only describe a problem is half a platform engineer.

Iteration 2 is the **capability-maturity** step where a steward gains the ability to *change* the cluster — `observe → reason → propose → HUMAN APPROVES → act`. The whole project's positioning depends on getting this boundary right. The repo has promised, in many canonical places, that MeshOps is **HITL-gated by default** and **not** a closed-loop autonomous remediator:

- `README.md` "Stack at a glance" — *HITL policy: No autonomous actuation — all write actions go through human gates (ADR-0011).*
- `030_design/01_use_cases.md` §8 — *"No closed-loop autonomous actuation. Every write has a HITL gate — including 'obvious' actions like scaling."* UC-10 **is** the HITL gate.
- `035_others/threat-model.md` — LLM05 (improper output handling) and **LLM06 (excessive agency)** both name the per-write HITL gate as the mitigation.
- `035_others/tech-stack.md` / `03_architecture.md` — the **HITL audit log** lives in **immutable Azure Storage**; *"ADR-0011 requires immutability."*

Forces at play:

- **Safety vs. generality.** Ram's model (correct) is scope-based, not verb-based: *reads are unrestricted; **any** mutation must be approved.* We must make "allow any write" safe without hand-maintaining a menu of allowed verbs.
- **The LLM is not trustworthy enough to actuate.** Prompt injection (LLM01) and excessive agency (LLM06) mean the model must never hold a tool that, on its own, changes the cluster.
- **We already committed to MCP as the single tool layer (ADR-0004).** The write path must go *through* MCP (aks-mcp), not a bespoke kubectl/ARM wrapper.
- **Demo reality.** Ram's lived test — *"create a test pod"* was refused in Iteration 1 — should now become *"here's what I'd do; approve?" → approve → done.* That interactive experience needs a synchronous approval surface, which is in tension with the earlier note that "HITL gates use GitHub PR review + Slack approval / no bespoke human-operator UI." This ADR reconciles that.

## Decision

**No steward ever executes a write autonomously. Reads are ungated; every mutation is intercepted, previewed to a human, and executed only after explicit approval — by deterministic code, never by the model.** This holds for *any* mutating operation (create / patch / delete / scale / apply / exec), not a fixed allowlist of verbs.

The gate is built from five load-bearing parts:

1. **Scope, not verbs, is the axis.**
   - **Read scope** (ungated): the steward may read anything its capability manifest allows — logs, resource/CR state, events, metrics — and answer freely.
   - **Write scope** (always gated): anything that mutates the cluster is a *proposal* until a human approves it.

2. **The LLM proposes; deterministic code applies.** The agent is wired with **read-only** MCP tools plus a single, **non-mutating** `propose_write` function tool. Calling `propose_write` does **not** touch the cluster — it records a *pending write* (operation, target, args, rationale) and returns `PENDING approval`. The model therefore has *no* tool that can actuate. A separate, non-LLM **executor** performs the approved write **through aks-mcp (`--access-level readwrite`)** — satisfying ADR-0004 (MCP is the only tool layer) — and only after a human approves.

3. **Preview via server dry-run.** Before a human decides, the gate renders the *concrete* effect using `kubectl --dry-run=server` (through aks-mcp), so the approver judges the real diff/manifest, not the model's prose description of it.

4. **RBAC is the hard backstop (defense-in-depth beneath the MCP capability layer).** The identity the executor uses is **write-but-bounded**: a namespaced Kubernetes `Role` scoped to the steward's workload namespace (`meshops-workloads`) that grants mutating verbs on the resources the steward operates, and **denies** Secrets, RBAC objects, and all cluster-scoped resources. So even an approved-but-wrong request *physically cannot* exceed scope. This replaces "bounded verb" safety with "bounded credential" safety — the pattern real platforms use.

5. **Immutable, append-only audit.** Every proposal, decision (approver identity + verdict), and outcome is written as a structured record (and an OTel span). The production sink is the **immutable Azure Storage** container already reserved in the tech stack; the application writes through an audit interface so the sink is swappable.

**Approval channels are pluggable, and this ADR refines the earlier "GitHub PR + Slack only" stance.** The gate exposes one approval abstraction with more than one channel:

| Channel | Nature | Use |
|---|---|---|
| **Interactive (in-steward chat approval)** | synchronous | live/operator-facing actions (Iteration 2's first surface — e.g. Ram's "create a test pod" demo) |
| **GitHub PR review** | asynchronous | change-as-code gates (e.g. Pipeline registry promotion, prompt-version PRs) |
| **Slack approval** | asynchronous | notify-and-approve for on-call flows |

All channels feed the *same* executor and the *same* immutable audit. The interactive chat card is therefore **not** a competing "bespoke operator console" — it is one approval channel on a shared gate.

**Capability flag.** Write scope is off by default (`write_enabled=false`), so a steward is byte-for-byte its Iteration-1 read-only self until write is deliberately enabled. Enabling write never removes the gate — it only makes the gate reachable.

## Alternatives considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **(a) Scope-based general gate: any write → HITL, LLM proposes / code applies, RBAC backstop (chosen)** | Matches the stated policy; safe for arbitrary writes without a verb menu; LLM can't actuate; writes still go through MCP; extensible to every steward | More moving parts (proposal store, executor, dry-run preview, bounded Role) | **Chosen** |
| (b) Curated allowlist of specific verbs (e.g. only `scale_workspace`, `create_diagnostic_pod`) | Each verb is trivially bounded and testable | Doesn't match "any write is gated"; every new capability needs code; brittle menu | Rejected — too narrow; contradicts the scope model |
| (c) Let the LLM hold a `readwrite` MCP tool, gate by prompting it to "ask first" | Simplest to wire | Prompt-only gate = no real gate; prompt injection / excessive agency defeats it; the model *can* actuate | Rejected — violates the core "model never actuates" invariant |
| (d) GitHub-PR-only gate (the original canonical stance) | Pure GitOps; immutable review trail for free | No live/interactive experience; every "create a test pod" becomes a PR round-trip; poor demo & poor fit for synchronous ops | Rejected as *sole* channel — kept as one channel among several |
| (e) Full closed-loop autonomy with post-hoc audit | "Impressive" autonomy | Exactly what the project promises *not* to be (§8); unacceptable blast radius; fails LLM06 | Rejected — non-negotiable |

## Consequences

**Positive:**

- The Iteration-1 → Iteration-2 arc becomes real and demonstrable on the *same* steward: the refusal Ram saw for "create a test pod" turns into propose → approve → act.
- The "model never actuates" invariant is structural (no write tool on the agent), not merely prompted — directly answering LLM06 (excessive agency) and LLM05 (improper output handling).
- Writes remain inside the MCP tool layer (ADR-0004); RBAC gives a second, credential-level backstop under the MCP capability layer.
- One gate + one audit serves every future steward and every approval channel — Iteration 2 for Pipeline/Quality/SRE inherits it.

**Negative / accepted trade-offs:**

- New infrastructure: a **write-but-bounded RBAC Role/RoleBinding** and (for production) an **immutable audit container**. The app ships an audit interface so the immutable sink can land incrementally.
- The proposal store adds a small amount of stateful surface (pending writes with TTL, single-use tokens) to an otherwise stateless chat.
- This ADR **supersedes the wording** in `01_use_cases.md` §8 ("HITL gates use GitHub PR review + Slack approval") and the "no bespoke human-operator UI" note: interactive chat approval is now an explicit, first-class channel. Those docs get a one-line pointer to this ADR.

**Things we'll need to revisit:**

- Iteration 3 may **auto-approve provably low-risk actions** — that is a *narrowing* of the gate for a proven-safe subset, decided in a later ADR; it does not weaken this one for anything else.
- If Entra Agent ID replaces per-SA Workload Identity, the "write-but-bounded identity" moves from a K8s Role to an agent-scoped role assignment; the *principle* is unchanged.
- The immutable audit sink (Azure Storage locked container) needs its own small ADR/infra task when it lands.

## References

- `README.md` — Stack at a glance, HITL policy row (ADR-0011).
- `030_design/01_use_cases.md` §8 (deliberate non-goals) and UC-10 (the HITL gate).
- `035_others/threat-model.md` — LLM05, LLM06 mitigations.
- `035_others/tech-stack.md`, `030_design/03_architecture.md` — immutable Azure Storage HITL audit log.
- ADR-0004 (MCP as the single tool layer) — the write path uses aks-mcp `readwrite`, not a bespoke wrapper.
- `040_iterations/iteration-01-read-only/README.md` — the two-axis maturity model; Iteration 2 is the gated-write row.
- [Azure/aks-mcp](https://github.com/Azure/aks-mcp) — `--access-level` (readonly / readwrite / admin).
- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/) — namespaced Role backstop.
- [kubectl server-side dry-run](https://kubernetes.io/docs/reference/using-api/server-side-apply/) — preview mechanism.

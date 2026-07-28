# Iteration 2 — Gated Write + HITL (across stewards)

*This folder is a **maturity phase**, not a steward. It collects the gated-write build of every steward that graduates from read-only. Read [Iteration 1's README](../iteration-01-read-only/README.md) first — it defines the two axes; this folder is the **next row down the depth axis**.*

## Where this sits on the two axes

MeshOps moves along two independent axes (see the Iteration-1 README): **steward = breadth** (which Ops domain) and **iteration = depth** (how much power an agent has). This folder is the **gated-write row**:

| Iteration | Capability | What the agent may do |
|---|---|---|
| Iteration 1 — read-only | `observe → reason → report` | Read its substrate, reason, explain. **Zero writes.** |
| **Iteration 2 — gated write (HITL)** | `observe → reason → propose → HUMAN APPROVES → act` | **Read anything (ungated); propose any mutation; execute it only after a human approves at the gate.** Per **ADR-0011: no autonomous actuation.** |
| Iteration 3+ — broader / auto-approved | wider action scope | Expand the action set, or auto-approve provably low-risk actions. |

## The one principle that defines this iteration

> **Read scope is ungated. Write scope is anything that mutates the cluster — and *every* write passes a human-in-the-loop gate.**

Not a menu of allowed verbs — *any* mutation (create / patch / delete / scale / apply / exec) is intercepted, previewed, and executed **only after a human approves**, by **deterministic code, never by the model.** The governing decision is [**ADR-0011**](../../035_others/decisions/0011-no-autonomous-actuation-hitl.md).

### The five load-bearing parts of the gate (see ADR-0011 §Decision)

1. **Scope, not verbs.** Reads flow freely; every write is a *proposal* until approved.
2. **The LLM proposes; deterministic code applies.** The agent holds only read-only MCP tools plus a single **non-mutating** `propose_write` tool that merely *records* a pending write. It has no tool that can actuate.
3. **Server dry-run preview.** The approver sees the real `--dry-run=server` diff, not the model's prose.
4. **RBAC backstop.** The executor uses a **write-but-bounded** identity (namespaced Role; no Secrets/RBAC/cluster-scoped verbs) so an approved-but-wrong request *physically cannot* exceed scope.
5. **Immutable, append-only audit.** Every proposal + decision + outcome is recorded (structured log + OTel span; immutable Azure Storage in production).

**Approval channels are pluggable** on one shared gate + audit: interactive **chat approval** (synchronous — this iteration's first surface), **GitHub PR** and **Slack** (asynchronous). ADR-0011 refines the earlier "PR + Slack only" stance.

**Capability flag.** Write scope is off by default (`write_enabled=false`) — a steward is byte-for-byte its Iteration-1 read-only self until write is deliberately enabled. Enabling write never removes the gate; it only makes the gate reachable.

## The matrix — where we are today

| Steward ↓ / Iteration → | **1 · read-only** | **2 · gated write (HITL)** | **3+ · broader** |
|---|---|---|---|
| **Inference** | ✅ [read-only](../iteration-01-read-only/inference/) | 🚧 [`inference/`](inference/) — first writer | ⬜ |
| **Pipeline** | ✅ [read-only](../iteration-01-read-only/pipeline/) | ⬜ (registry promotion via PR channel) | ⬜ |
| **Quality** | ✅ [read-only](../iteration-01-read-only/quality/) | ⬜ (prompt-version PR) | ⬜ |
| **SRE** | ⬜ | ⬜ | ⬜ |
| **Gateway** | ⬜ | ⬜ | ⬜ |
| **Security** | ⬜ | ⬜ | ⬜ |

**Inference is the first steward to graduate to gated write.** The demo that motivated it: in Iteration 1, asking the steward to *"create a test pod"* was refused ("I'm read-only"). In Iteration 2, the same request becomes *propose → preview → you approve → it acts → it's audited.*

## Documents in this folder (inference)

| Doc | Purpose |
|---|---|
| [`inference/01_use_case.md`](inference/01_use_case.md) | The story of the gated-write slice — what the steward now does and where it stops. |
| `inference/02_implementation_guide.md` | Every file written for the write gate, with real code (inference house style). |
| `inference/03_test_cases_manual.md` | Manual test script — the propose → approve → act and propose → reject flows. |
| `inference/04_test_cases_automated.md` | The automated test suite for the gate, schema, executor, and RBAC-denied path. |
| `inference/05_deployment_guide.md` | Enabling `write_enabled`, applying the bounded RBAC role, and going live. |

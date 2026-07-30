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

**Approval channels are pluggable** on one shared gate + audit: interactive **chat approval** (synchronous — this iteration's first surface), **GitHub PR** (asynchronous — merge = approve, close = reject) and **Slack** (designed, not yet built). ADR-0011 refines the earlier "PR + Slack only" stance. The pipeline & quality writers run live on the **GitHub-PR** channel.

**Shared HITL spine.** Inference (the first writer) grew its gate in-tree. To avoid three copies, the domain-agnostic machinery is now the shared package **[`src/stewards/hitl/`](../../src/stewards/hitl/)** (`Proposal`/`WriteGate`/`Applier`/`AuditSink`, pluggable `channels.py`, `serve_support.py`). Each steward supplies only its two domain pieces — a `Proposal` subclass and an `Applier`. Pipeline and quality are built entirely on this spine; inference keeps its original copy for zero-regression.

**Capability flag.** Write scope is off by default (`write_enabled=false`) — a steward is byte-for-byte its Iteration-1 read-only self until write is deliberately enabled. Enabling write never removes the gate; it only makes the gate reachable.

## The matrix — where we are today

| Steward ↓ / Iteration → | **1 · read-only** | **2 · gated write (HITL)** | **3+ · broader** |
|---|---|---|---|
| **Inference** | ✅ [read-only](../iteration-01-read-only/inference/) | ✅ [`inference/`](inference/) — first writer (chat + PR) | ⬜ |
| **Pipeline** | ✅ [read-only](../iteration-01-read-only/pipeline/) | ✅ [`pipeline/`](pipeline/) — registry promotion (PR channel) | ⬜ |
| **Quality** | ✅ [read-only](../iteration-01-read-only/quality/) | ✅ [`quality/`](quality/) — trace annotation (PR channel) | ⬜ |
| **SRE** | ✅ [read-only](../iteration-01-read-only/sre/) | ✅ [`sre/`](sre/) — Deployment scale (PR channel) | ⬜ |
| **Gateway** | ✅ [read-only](../iteration-01-read-only/gateway/) | ✅ [`gateway/`](gateway/) — route budget cap (PR channel) | ⬜ |
| **Security** | ✅ [read-only](../iteration-01-read-only/security/) | ✅ [`security/`](security/) — PR quarantine (chat channel) | ⬜ |

**Six stewards now graduated to gated write.** Inference was first (*"create a test pod"* → propose/preview/approve/act). Pipeline promotes a model version in the MLflow registry; Quality annotates a Langfuse trace with a reviewed score; **SRE is the first correlation/AIOps writer**, and its gated write is Deployment replica scale; **Gateway is the routing/cost writer**, and its gated write is a LiteLLM route budget cap; **Security is the first SecOps writer**, and its gated write is GitHub PR quarantine. Each follows **propose → human approves → deterministic code applies it → it's audited**, never the model.

## Documents in this folder

Each writer has the same five-doc bundle (use-case → implementation → manual tests → automated tests → deployment):

| Steward | Bundle |
|---|---|
| **Inference** | [`inference/`](inference/) — [use case](inference/01_use_case.md) · [implementation](inference/02_implementation_guide.md) · [manual tests](inference/03_test_cases_manual.md) · [automated tests](inference/04_test_cases_automated.md) · [deployment](inference/05_deployment_guide.md) |
| **Pipeline** | [`pipeline/`](pipeline/) — [use case](pipeline/01_use_case.md) · [implementation](pipeline/02_implementation_guide.md) · [manual tests](pipeline/03_test_cases_manual.md) · [automated tests](pipeline/04_test_cases_automated.md) · [deployment](pipeline/05_deployment_guide.md) |
| **Quality** | [`quality/`](quality/) — [use case](quality/01_use_case.md) · [implementation](quality/02_implementation_guide.md) · [manual tests](quality/03_test_cases_manual.md) · [automated tests](quality/04_test_cases_automated.md) · [deployment](quality/05_deployment_guide.md) |
| **SRE** | [`sre/`](sre/) — [use case](sre/01_use_case.md) · [implementation](sre/02_implementation_guide.md) · [manual tests](sre/03_test_cases_manual.md) · [automated tests](sre/04_test_cases_automated.md) · [deployment](sre/05_deployment_guide.md) |
| **Gateway** | [`gateway/`](gateway/) — [use case](gateway/01_use_case.md) · [implementation](gateway/02_implementation_guide.md) · [manual tests](gateway/03_test_cases_manual.md) · [automated tests](gateway/04_test_cases_automated.md) · [deployment](gateway/05_deployment_guide.md) |
| **Security** | [`security/`](security/) — [use case](security/01_use_case.md) · [implementation](security/02_implementation_guide.md) · [manual tests](security/03_test_cases_manual.md) · [automated tests](security/04_test_cases_automated.md) · [deployment](security/05_deployment_guide.md) |

> The **implementation guides** for pipeline and quality describe the shared [`stewards.hitl`](../../src/stewards/hitl/) package once (in the [pipeline guide](pipeline/02_implementation_guide.md)) and then only their domain-specific `Proposal`/`Applier`/tool — read the pipeline implementation guide first if you want the full spine walkthrough.

# Glossary — MeshOps

**Why this exists:** DevOps and AI overload several of the same words to mean different things ("deployment", "model", "rollback"). MeshOps adds another layer — agents, MCP, multi-agent-system terms. This page resolves the ambiguity so a DevOps reader doesn't misread an AI sentence — and vice versa.


---

## 1. DevOps ↔ AI collision terms

These mean different things in each world. **Disambiguate every time.**

| Term | In DevOps it means... | In AI/ML it means... | In MeshOps... |
|---|---|---|---|
| **Deployment** | A Kubernetes `Deployment` resource managing replicas of a pod | The act of putting a trained model behind a serving endpoint | Both. We say **"model deployment"** for the AI sense, **"K8s Deployment"** for the DevOps sense |
| **Model** | (no fixed meaning) | A trained neural network — weights + architecture | Always the AI sense |
| **Rollback** | Revert a Deployment to the previous version | Revert to the previous *model* version | Both. We say **"model rollback"** explicitly |
| **Environment** | dev / staging / prod cluster | The runtime where inference happens | DevOps sense; the AI runtime is the **"inference workload plane"** |
| **Drift** | Configuration drift (cluster state vs. declared) | Data/concept drift (input distribution shifts over time) | We say **"config drift"** vs. **"data drift"** vs. **"faithfulness drift"** |
| **Pipeline** | CI/CD pipeline | ML training / fine-tuning pipeline | Disambiguated: **"CI pipeline"**, **"fine-tuning pipeline"** |
| **Serving** | (not a DevOps term) | Running a model behind an inference API | AI sense always |
| **Registry** | Container registry (ACR, Docker Hub) | Model registry (MLflow, Azure ML) | We say **"container registry"** vs. **"model registry"** |
| **Plane** | (not a DevOps term commonly) | (not an AI term) | One of MeshOps's 5 logical layers — see [architecture.md §1](architecture.md#1-the-five-planes) |

## 2. AI & LLM terms

| Term | Meaning |
|---|---|
| **Token** | The sub-word unit an LLM operates on. ~4 chars of English per token |
| **Context window** | Max tokens (input + output) a model can process per call |
| **Embedding** | Vector representation of text used for similarity search |
| **Vector store** | Database optimised for nearest-neighbour search over embeddings |
| **RAG (Retrieval-Augmented Generation)** | Pattern where a retrieval step pulls relevant chunks from a corpus and feeds them to the LLM as context before generation |
| **Chunk** | A bounded slice of a source document, indexed independently |
| **Prompt** | The full text sent to the LLM (system prompt + user input + retrieved context + few-shot) |
| **System prompt** | Persistent instructions that shape the LLM's behaviour |
| **Tool / function calling** | LLM emits a structured call to a named function; host runs it and returns the result back into the prompt |
| **Eval (evaluation)** | Automated quality measurement of LLM outputs against a fixed test set |
| **Faithfulness** | Whether an answer is grounded in the retrieved context (RAG-specific) |
| **Hallucination** | LLM output that is fluent but factually wrong or unsupported by context |
| **Guardrails** | Runtime input/output filters enforcing safety, format, or domain rules |
| **Fine-tuning** | Continuing training of a pretrained model on a smaller, task-specific dataset |
| **LoRA / QLoRA** | Parameter-efficient fine-tuning; QLoRA adds 4-bit quantization |
| **SLM (Small Language Model)** | LLMs in the ~1B–10B parameter range (e.g., Phi-4-mini) |
| **vLLM** | High-throughput LLM inference server with continuous batching and paged attention |
| **KV cache** | The cached key-value tensors from prior tokens, enabling fast autoregressive decoding |
| **Prompt injection** | An attack where input manipulates the LLM into ignoring its system prompt |
| **DPO (Direct Preference Optimization)** | Preference-tuning alternative to RLHF *(advanced track)* |

## 3. Agentic + MCP terms

| Term | Meaning |
|---|---|
| **Agent** | An LLM-driven loop that observes, reasons, calls tools, and iterates toward a goal |
| **Multi-agent system (MAS)** | Multiple specialised agents coordinating, typically via an orchestrator |
| **Group-chat** | An orchestration pattern (MAF, AutoGen) where multiple agents converse in a shared message log |
| **MCP (Model Context Protocol)** | Open protocol for agents to call external tools through standardised servers |
| **MCP server** | Process that exposes one or more tools to MCP-aware agents, with capability scoping |
| **Capability manifest** | A per-agent, signed declaration of which MCP tools it's allowed to call |
| **Confused deputy** | Security pattern where an agent with high privileges is tricked into using them on an attacker's behalf — see [planes-and-mcp.md §4](planes-and-mcp.md#4-the-confused-deputy-defense) |
| **HITL (Human-in-the-loop) gate** | A required human approval before a write action — see ADR-0011 |
| **Steward** | A MeshOps-specific term: a specialist agent owning one -Ops surface (Inference / Pipeline / Quality / SRE / Gateway / Security) |
| **MAS attack class** | Multi-agent-specific threats not in OWASP LLM Top-10 — see [threat-model.md §3](threat-model.md#3-mas-multi-agent-system-extensions) |

## 4. -Ops surfaces

| Surface | What it owns | MeshOps owner |
|---|---|---|
| **LLMOps** | LLM serving, eval, prompt versioning, routing, cost | Inference + Quality + Gateway |
| **MLOps** | Dataset → train → eval → registry → promote lifecycle | Pipeline |
| **AIOps** | AI-augmented incident detection, RCA, observability correlation | SRE |
| **SecOps** | Adversarial input defense, supply-chain integrity, audit | Security |
| **FinOps** | Cost attribution, budget enforcement | (advanced track — currently inside Gateway) |
| **AgentOps** | Operating agentic systems (cousin term to MeshOps) | (the *practice* MeshOps is *about*) |

## 5. MeshOps-specific terms

| Term | Meaning |
|---|---|
| **MeshOps** | The mesh-based operations discipline this project defines and demonstrates |
| **Steward** | See §3 |
| **Driving steward** | The steward primarily responsible for a cross-steward use case |
| **Participating steward** | A steward that contributes to a cross-steward use case but doesn't drive it |
| **Group-chat orchestrator** | Thin MAF agent that routes cross-steward handoffs |
| **Iteration N** | Review cadence (iteration 1 = current planning, iteration 2 = Phase 0 kickoff, etc.) |
| **Phase Pn** | A 5–8 week build phase in the roadmap (P0–P4) |
| **Lab cluster** | The sandbox AKS cluster in `rg-meshops-sandbox` |
| **Runbook RAG corpus** | The collection of runbooks the agents consume via RAG; populated from public Microsoft Learn docs only |
| **Eval gate** | A CI step that fails a PR merge if eval regresses below threshold |
| **Canary policy** | The 0%-shadow → 5% → 50% → 100% rollout pattern with HITL gates at each step |
| **Capability manifest** | Per-steward, signed declaration of allowed MCP tools and their verbs |
| **MAS01..MAS05** | Multi-agent-system threat IDs from [threat-model.md §3](threat-model.md#3-mas-multi-agent-system-extensions) |

## 6. Microsoft / Azure stack terms

| Term | Meaning |
|---|---|
| **AKS** | Azure Kubernetes Service |
| **ACR** | Azure Container Registry |
| **AOAI** | Azure OpenAI Service |
| **Azure AI Foundry** | Microsoft's AI platform (model catalog, Agents, Prompt Flow, Evaluations) |
| **Foundry Agent Service** | Managed agent runtime within Foundry |
| **MAF** | Microsoft Agent Framework — open-source multi-agent runtime |
| **Semantic Kernel (SK)** | Microsoft's agentic SDK / skill framework, often embedded inside MAF |
| **KAITO** | Kubernetes AI Toolchain Operator — Microsoft OSS, AKS managed add-on for LLM/SLM/RAG |
| **Workspace (KAITO sense)** | A KAITO custom resource that declares a model serving / fine-tune / RAG runtime |
| **InferencePool / EPP** | KAITO + Gateway API Inference Extension construct for KV-cache-aware routing |
| **Entra ID** | Microsoft's identity service (formerly Azure AD) |
| **Entra Agent ID** | Agent-specific identity construct (advanced track) |
| **Defender for Cloud** | Microsoft's cloud security posture & threat protection |

## 7. Acronym index

ACR — Azure Container Registry · ADR — Architecture Decision Record · AI-300 — Microsoft Certified: MLOps Engineer Associate · AIOps — AI-augmented Operations · AKS — Azure Kubernetes Service · AOAI — Azure OpenAI · CKA/CKAD/CKS — Certified Kubernetes Administrator / Application Developer / Security · CRD — Custom Resource Definition · EPP — Endpoint Picker (KAITO) · HITL — Human-in-the-loop · IaC — Infrastructure as Code · KAITO — Kubernetes AI Toolchain Operator · KV — Key Vault · LLM — Large Language Model · LLMOps — LLM Operations · LoRA — Low-Rank Adaptation · MAF — Microsoft Agent Framework · MAS — Multi-Agent System · MCP — Model Context Protocol · MLOps — Machine Learning Operations · NAP — Node Auto Provisioner · OWASP — Open Web Application Security Project · PVC — Persistent Volume Claim · QLoRA — Quantized LoRA · RAG — Retrieval-Augmented Generation · RBAC — Role-Based Access Control · SecOps — Security Operations · SK — Semantic Kernel · SLM — Small Language Model · SLO — Service Level Objective

## Sources

- [OWASP LLM Top 10](https://owasp.org/www-project-top-10-for-large-language-model-applications/)
- [Model Context Protocol](https://modelcontextprotocol.io)
- [Microsoft Agent Framework](https://learn.microsoft.com/en-us/agent-framework/)
- [KAITO project](https://github.com/kaito-project/kaito)


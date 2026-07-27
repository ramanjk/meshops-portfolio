# Iteration-02 — Pipeline Steward (`hello-pipeline`)

*Concise guide. The full 5-doc bundle (use-case / test-cases / deployment) will
follow the iteration-01 pattern later. This captures what was built, why, and how
to run it.*

## What this is

The **Pipeline Steward** is MeshOps' second agent. Like the Inference Steward it
is a **read-only** `observe → reason → report` agent, but its substrate is an
**MLflow Model Registry** instead of a KAITO Workspace. It watches how a
registered model's versions move through the promotion lifecycle
(`None → Staging → Production → Archived`) and explains promotion-readiness — it
**never** writes to the registry (no stage transitions, no register/delete).

It maps to **UC-03** (MLOps) in the six-steward mesh. The propose → HITL →
promote tail of UC-03 is deliberately deferred to a later iteration; iteration-02
ships only the read-only observe slice, mirroring iteration-01's discipline.

## How it differs from iteration-01

| Aspect | Inference (iter-01) | Pipeline (iter-02) |
|---|---|---|
| Substrate | KAITO Workspace (Kubernetes CR) | MLflow Model Registry (REST 2.0) |
| Tools | `aks-mcp` + `prom-mcp` | `mlflow-mcp` (one, HTTP-only) |
| Kube RBAC | Broad cluster read (`view` + custom) | **None** — reads MLflow over HTTP, not the kube API |
| Output schema | `InferenceObservation` | `PipelineObservation` |
| Workload Identity | AOAI + Key Vault | AOAI + Key Vault (reuses `msi-hello-inference`) |

Everything else (MAF + Azure OpenAI `gpt-4.1`, Langfuse OTel tracing, Prometheus
exporter, the empty-file prompt fallback, the three no-write guarantees, the
chat server + LoadBalancer exposure) is the same shape as iteration-01.

## The three no-write guarantees (unchanged philosophy)

1. **Tools** — `mlflow-mcp` exposes only read verbs
   (`list_registered_models`, `get_registered_model`, `list_model_versions`).
2. **Persona** — the system/chat prompts forbid any registry write and tell the
   steward to decline promotion requests.
3. **Schema** — `PipelineObservation` has no field to express a write, and its
   `requires_hitl` validator hard-fails on `True`.

## Components

```
src/stewards/pipeline/
  settings.py   # pydantic-settings: AOAI, Langfuse, MLFLOW_TRACKING_URI, REGISTERED_MODEL_NAME
  schemas.py    # PipelineObservation (narrow, no-write validator)
  agent.py      # MAF agent; one mlflow-mcp tool; observe→reason→report + chat/loop/one-shot modes
  serve.py      # FastAPI chat server (/chat, /, /healthz) — same UX as iter-01
  __main__.py

src/mcp_servers/mlflow_mcp/
  server.py     # FastMCP shim: read-only httpx calls to MLflow REST /api/2.0/mlflow
  __main__.py

prompts/
  pipeline-steward.system.md   # observe/report JSON persona
  pipeline-steward.chat.md     # conversational persona (non-negotiable identity)

helm/pipeline/                 # dedicated chart, isolated from the steward-1 chart
  Chart.yaml, values.yaml
  prompts -> ../../prompts     # symlink so .Files.Get can read repo-root prompts
  templates/{deployment,service,ingress,secretproviderclass,podmonitor}.yaml
  extras/mlflow.yaml           # in-cluster MLflow substrate (sqlite + PVC)
  extras/mlflow-seed.yaml      # seeds phi-4-mini-meshops with 3 staged versions
```

The `Dockerfile` and `pyproject.toml` are shared: the image bakes **all**
stewards, and the Helm `command:` selects `python -m stewards.pipeline`.

## Substrate: in-cluster MLflow

A lab-grade single-replica MLflow server (`ghcr.io/mlflow/mlflow:v2.16.2`) with a
sqlite backend store (holds registered models + versions) and a local filesystem
artifact store, both on one `managed-csi` PVC. Runs with `--workers=1` to stay
inside a 1.5Gi memory limit (4 default gunicorn workers OOM at 512Mi). Exposed as
a ClusterIP Service on `:5000` — **no auth**, in-cluster only.

Seeded model **`phi-4-mini-meshops`**: v1 `Archived`, v2 `Production`,
v3 `Staging` (one candidate awaiting promotion).

## Deploy

```bash
# 0. Prereqs: AKS + jumpbox running, ACR/KV/AOAI standing (see iter-01 §05).

# 1. Substrate — MLflow + seed data
kubectl apply -f helm/pipeline/extras/mlflow.yaml
kubectl -n mlflow rollout status deploy/mlflow --timeout=150s
kubectl apply -f helm/pipeline/extras/mlflow-seed.yaml
kubectl -n mlflow wait --for=condition=complete job/mlflow-seed --timeout=180s

# 2. Image (all stewards baked in)
az acr build --registry acrmeshops --image meshops/hello-pipeline:0.0.1 .

# 3. Workload Identity — federate the existing UAMI to the new SA subject
#    (the msi already has AOAI + Key Vault access)
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create --name fic-hello-pipeline \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-pipeline \
  --audience api://AzureADTokenExchange

# 4. Deploy the steward
helm upgrade --install hello-pipeline helm/pipeline -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-pipeline \
  --set image.tag=0.0.1 \
  --set serviceAccount.clientId=<msi-hello-inference clientId> \
  --set keyVault.name=<kv name> \
  --set keyVault.tenantId=<tenant id> \
  --set env.azureOpenAiEndpoint=https://<aoai>.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1
```

### Public LoadBalancer (optional, mirrors iter-01)

The BYO `snet-aks` subnet has an AKS-auto-created NSG
(`vnet-meshops-lab-snet-aks-nsg-southcentralus`, **not** Terraform-managed) whose
`DenyAllInbound` blocks the public LB even though the node NSG gets the
cloud-provider allow rule. Add an inbound rule for the assigned EXTERNAL-IP:

```bash
az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-pipeline-chat-lb-inbound --priority 510 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes <EXTERNAL-IP> --destination-port-ranges 8080
```

The endpoint has **no auth**. To lock it down, set
`chat.service.loadBalancerSourceRanges` and narrow this rule's source.

## Verify (E2E)

```bash
# Identity
curl -sX POST http://<EXTERNAL-IP>:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"Who are you?"}'
# -> "I'm the Pipeline Steward — I watch model promotion across ... MLflow ..."

# Live registry read
curl -sX POST http://<EXTERNAL-IP>:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"What stage is each version of phi-4-mini-meshops in?"}'
# -> v3 Staging (awaiting promotion), v2 Production, v1 Archived

# Read-only guardrail
curl -sX POST http://<EXTERNAL-IP>:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"Promote version 3 to Production now."}'
# -> politely declines; explains it is read-only
```

Each turn emits a `trace_id` visible in Langfuse.

## Tests

```bash
pytest -q          # unit: pipeline schema + settings + prompt loading; integration: boot
```

## Cost / shutdown

The MLflow Deployment (+PVC), the `hello-pipeline` pod, and its public LB all
accrue cost. On overnight shutdown: `az aks stop` handles compute; delete the
`hello-pipeline-chat` Service to free the LB public IP (the NSG rule persists but
is harmless). The seeded MLflow data survives on its PVC.

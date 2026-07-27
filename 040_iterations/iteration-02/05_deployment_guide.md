# Iteration-02 — Deployment Guide: Shipping the Pipeline Steward

*Audience: Ram, standing up `hello-pipeline` on the lab AKS cluster. Assumes the iteration-01 substrate (AKS, ACR, Key Vault, Azure OpenAI, Langfuse, the `msi-hello-inference` managed identity) is already standing.*

Five moves: stand up the registry, seed it, build the image, wire Workload Identity, deploy. Then verify and (when you're done) tear down the billable bits.

## Prerequisites

| Thing | Value (this lab) |
|---|---|
| Resource group | `rg-meshops-sandbox` |
| AKS cluster | `aks-meshops-lab` (region `southcentralus`) |
| ACR | `acrmeshops` (`acrmeshops.azurecr.io`) |
| Managed identity (reused) | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault | `kv-meshops-3q6qct`, tenant `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Azure OpenAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |

The Pipeline steward **reuses** the Inference steward's managed identity (it already has Azure OpenAI + Key Vault access), so no new role assignments — just one new federated credential (step 3).

---

## Step 1 — Stand up the MLflow registry

```bash
kubectl apply -f helm/pipeline/extras/mlflow.yaml
kubectl -n mlflow rollout status deploy/mlflow --timeout=150s
```

This creates namespace `mlflow`, a 5Gi `managed-csi` PVC, the MLflow server Deployment (`--workers=1`, 1.5Gi limit), and a ClusterIP Service on `:5000`.

> If the pod goes `Pending` on "Insufficient cpu," the cluster autoscaler adds a node — wait ~90s.

## Step 2 — Seed the registry

```bash
kubectl apply -f helm/pipeline/extras/mlflow-seed.yaml
kubectl -n mlflow wait --for=condition=complete job/mlflow-seed --timeout=180s
kubectl -n mlflow logs job/mlflow-seed | tail
# expect: v1 -> Archived, v2 -> Production, v3 -> Staging
```

The seed is deterministic (it deletes the model first), so it's safe to re-run for a clean reseed.

## Step 3 — Build & push the image

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-pipeline:0.0.1 \
  --image meshops/hello-pipeline:latest .
```

Server-side build (no local Docker). The image bakes all stewards.

## Step 4 — Federate Workload Identity to the new ServiceAccount

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-pipeline \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-pipeline \
  --audience api://AzureADTokenExchange
```

This lets the `hello-pipeline` ServiceAccount exchange its token for the existing identity — so the pod authenticates to Azure OpenAI and pulls Langfuse secrets from Key Vault without any stored key.

## Step 5 — Deploy the steward

```bash
helm upgrade --install hello-pipeline helm/pipeline -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-pipeline \
  --set image.tag=0.0.1 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1

kubectl -n meshops rollout status deploy/hello-pipeline --timeout=150s
```

### Step 5b — Public LoadBalancer access (the subnet-NSG gotcha)

The chat Service is `type: LoadBalancer`. Get its IP:

```bash
kubectl -n meshops get svc hello-pipeline-chat -w   # wait for EXTERNAL-IP
```

The BYO `snet-aks` subnet has an AKS-auto-created NSG
(`vnet-meshops-lab-snet-aks-nsg-southcentralus`, **not** Terraform-managed) whose
`DenyAllInbound` blocks the public LB even though the node NSG gets the
cloud-provider allow rule. Add an inbound rule for the assigned IP:

```bash
az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-pipeline-chat-lb-inbound --priority 510 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes <EXTERNAL-IP> --destination-port-ranges 8080
```

> **Security:** the endpoint has **no auth**. To restrict it, set
> `chat.service.loadBalancerSourceRanges` in the Helm values and narrow the NSG
> rule's `--source-address-prefixes` to your egress CIDRs.

---

## Verify

```bash
kubectl -n meshops get pods -l app.kubernetes.io/name=hello-pipeline   # 1/1 Running
kubectl -n meshops logs -l app.kubernetes.io/name=hello-pipeline | tail
# expect: "persona loaded, MCP tools connected" + WI clientId resolved

curl -s http://<EXTERNAL-IP>:8080/healthz          # {"status":"ok"}
curl -sX POST http://<EXTERNAL-IP>:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"What stage is each version of phi-4-mini-meshops in?"}'
# expect: v3 Staging, v2 Production, v1 Archived + a trace_id
```

Then walk `03_test_cases_manual.md` for the full prompt suite.

---

## Teardown (billing hygiene)

Everything here accrues cost — the MLflow Deployment + PVC, the steward pod, and the public LB.

```bash
# Free the public LB IP (biggest ongoing charge after compute):
kubectl -n meshops delete svc hello-pipeline-chat

# Full stop for the day (compute):
az aks stop -n aks-meshops-lab -g rg-meshops-sandbox
az vm deallocate -n <jumpbox> -g rg-meshops-sandbox
```

Notes:
- The `allow-pipeline-chat-lb-inbound` NSG rule persists but is harmless (nothing listens once the Service is gone).
- The seeded MLflow data survives on its PVC across `az aks stop`/`start`.
- To remove the steward entirely: `helm uninstall hello-pipeline -n meshops`. To remove the registry: `kubectl delete namespace mlflow` (this **deletes** the PVC and seed data).

## Rollback

```bash
helm rollback hello-pipeline -n meshops    # previous revision
# or
helm uninstall hello-pipeline -n meshops   # remove the steward (leaves MLflow intact)
```

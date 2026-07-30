# Iteration 1 (Read-Only) — Deployment Guide: Shipping the SRE Steward

*Audience: Ram, standing up `hello-sre-iter1` on the lab AKS cluster. Assumes AKS, ACR, Key Vault, Azure OpenAI, Langfuse, Azure Managed Prometheus, and the reused `msi-hello-inference` identity already exist.*

Five moves: build the image, federate Workload Identity, deploy with all values explicit, expose the LoadBalancer through the subnet NSG, verify.

## Prerequisites

| Thing | Value (this lab) |
|---|---|
| Resource group | `rg-meshops-sandbox` |
| AKS cluster | `aks-meshops-lab` (region `southcentralus`) |
| ACR | `acrmeshops` (`acrmeshops.azurecr.io`) |
| Managed identity (reused) | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault | `kv-meshops-3q6qct`, tenant `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Azure OpenAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1`, capacity `100` |
| AKS resource id | `/subscriptions/d8f26eb0-452d-42ff-89a3-8290f00e132a/resourceGroups/rg-meshops-sandbox/providers/Microsoft.ContainerService/managedClusters/aks-meshops-lab` |
| Prom query URL | `https://amw-meshops-lab-hnfbd3dfb4g6f6gw.southcentralus.prometheus.monitor.azure.com` |
| OIDC issuer | `https://southcentralus.oic.prod-aks.azure.com/16b3c013-d300-468d-ac64-7eda0820b6d3/b1af5beb-9ed5-421c-ac7e-60a967a15f11/` |

---

## Step 1 — Build & push the image

One Dockerfile bakes all stewards plus `gh 2.65.0`, `kubectl`, and `aks-mcp`.

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-sre:0.1.0 \
  --image meshops/hello-sre:latest .
```

---

## Step 2 — Federate Workload Identity to the iter-1 ServiceAccount

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-sre-iter1 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-sre-iter1 \
  --audience api://AzureADTokenExchange
```

Live issuer: `https://southcentralus.oic.prod-aks.azure.com/16b3c013-d300-468d-ac64-7eda0820b6d3/b1af5beb-9ed5-421c-ac7e-60a967a15f11/`.

---

## Step 3 — Deploy read-only `hello-sre-iter1`

> **GOTCHA:** do **not** use `--reuse-values` on the first install or when changing chart defaults. Pass all keys explicitly so new values (Prometheus URL, GitHub/channel defaults, write flags) do not silently stay empty.

```bash
helm upgrade --install hello-sre-iter1 helm/sre -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-sre \
  --set image.tag=0.1.0 \
  --set serviceAccount.name=hello-sre-iter1 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set env.aksResourceId=/subscriptions/d8f26eb0-452d-42ff-89a3-8290f00e132a/resourceGroups/rg-meshops-sandbox/providers/Microsoft.ContainerService/managedClusters/aks-meshops-lab \
  --set env.azureMonitorWorkspaceQueryUrl=https://amw-meshops-lab-hnfbd3dfb4g6f6gw.southcentralus.prometheus.monitor.azure.com \
  --set writeEnabled=false

kubectl -n meshops rollout status deploy/hello-sre-iter1 --timeout=150s
```

---

## Step 4 — Public LoadBalancer access + subnet NSG rule

The live iter-1 Service is exposed at `20.118.97.250:8080`.

```bash
kubectl -n meshops get svc hello-sre-iter1-chat

az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-sre-iter1 --priority 560 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes 20.118.97.250 --destination-port-ranges 8080
```

> **Security:** the chat endpoint has no auth. Narrow `chat.service.loadBalancerSourceRanges` and the NSG source prefix for anything beyond a lab demo.

---

## Step 5 — Verify

```bash
kubectl -n meshops get pods -l app.kubernetes.io/name=hello-sre-iter1
# expect: 1/1 Running

curl -s http://20.118.97.250:8080/healthz
# expect: {"status":"ok"}

curl -sX POST http://20.118.97.250:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"Who are you?"}'
# expect: "I'm the SRE Steward..."
```

Then run `03_test_cases_manual.md`.

---

## Gotcha: Langfuse PostgreSQL CSI reattach after `az aks start`

If the cluster was stopped and started, Langfuse may come back with its PostgreSQL CSI mount stale. The symptom is SRE/Quality/Langfuse reads failing even though the steward pod is healthy. Reattach by deleting the StatefulSet pod and letting it recreate:

```bash
kubectl -n langfuse delete pod langfuse-postgresql-0
kubectl -n langfuse rollout status statefulset/langfuse-postgresql --timeout=180s
```

---

## Teardown / cost hygiene

```bash
kubectl -n meshops delete svc hello-sre-iter1-chat
az network nsg rule delete -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-sre-iter1
az aks stop -n aks-meshops-lab -g rg-meshops-sandbox
```

## Rollback

```bash
helm rollback hello-sre-iter1 -n meshops
# or
helm uninstall hello-sre-iter1 -n meshops
```

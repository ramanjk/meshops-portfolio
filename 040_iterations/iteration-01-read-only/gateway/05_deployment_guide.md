# Iteration 1 (Read-Only) — Deployment Guide: Shipping the Gateway Steward

*Audience: Ram, standing up `hello-gateway-iter1` on the lab AKS cluster. Assumes AKS, ACR, Key Vault, Azure OpenAI, Langfuse, and the reused `msi-hello-inference` identity already exist.*

Five moves: ensure the LiteLLM substrate + secret, build the image, federate Workload Identity, deploy with all values explicit, expose the LoadBalancer through the subnet NSG, verify.

## Prerequisites

| Thing | Value (this lab) |
|---|---|
| Resource group | `rg-meshops-sandbox` |
| AKS cluster | `aks-meshops-lab` (region `southcentralus`) |
| ACR | `acrmeshops` (`acrmeshops.azurecr.io`) |
| Managed identity (reused) | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault | `kv-meshops-3q6qct`, tenant `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Azure OpenAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| LiteLLM substrate | namespace `meshops-workloads`, Service `litellm:4000`, ConfigMap `litellm-config` key `config.yaml` |
| Gateway image | `acrmeshops.azurecr.io/meshops/hello-gateway:0.1.0` |

---

## Step 0 — LiteLLM substrate and master key

The proxy fronts two logical routes over Azure OpenAI `gpt-4.1`:

| Route | Upstream | Budget cap |
|---|---|---|
| `chat-premium` | `azure/gpt-4.1` | `$50` |
| `chat-economy` | `azure/gpt-4.1` | `$5` |

The AOAI resource has `disableLocalAuth=true`, so the proxy authenticates keyless with Workload Identity / Entra ID (`enable_azure_ad_token_refresh`). The LiteLLM master key is stored in Key Vault as `litellm-master-key` and projected to the steward as `LITELLM_MASTER_KEY`.

> **GOTCHA:** Key Vault is private. The live secret was set from the jumpbox with `az vm run-command --identity` because the build host was network-blocked with `ForbiddenByConnection`.

---

## Step 1 — Build & push the image

One Dockerfile bakes all stewards plus `gh 2.65.0`, `kubectl`, and the in-repo `litellm_mcp` shim.

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-gateway:0.1.0 \
  --image meshops/hello-gateway:latest .
```

---

## Step 2 — Federate Workload Identity to the iter-1 ServiceAccount

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-gateway-iter1 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-gateway-iter1 \
  --audience api://AzureADTokenExchange
```

---

## Step 3 — Deploy read-only `hello-gateway-iter1`

> **GOTCHA:** do **not** use `--reuse-values` on the first install or when changing chart defaults. Pass all keys explicitly so new values (LiteLLM URL, budget defaults, write flags) do not silently stay empty.

```bash
helm upgrade --install hello-gateway-iter1 helm/gateway -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-gateway \
  --set image.tag=0.1.0 \
  --set serviceAccount.name=hello-gateway-iter1 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set litellm.baseUrl=http://litellm.meshops-workloads.svc.cluster.local:4000 \
  --set writeEnabled=false

kubectl -n meshops rollout status deploy/hello-gateway-iter1 --timeout=150s
```

---

## Step 4 — Public LoadBalancer access + subnet NSG rule

The live iter-1 Service is exposed at `48.192.170.188:8080`.

```bash
kubectl -n meshops get svc hello-gateway-iter1-chat

az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-gateway-iter1 --priority 580 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes 48.192.170.188 --destination-port-ranges 8080
```

> **Security:** the chat endpoint has no auth. Narrow `chat.service.loadBalancerSourceRanges` and the NSG source prefix for anything beyond a lab demo.

---

## Step 5 — Verify

```bash
kubectl -n meshops get pods -l app.kubernetes.io/name=hello-gateway-iter1
# expect: 1/1 Running

curl -s http://48.192.170.188:8080/healthz
# expect: {"status":"ok"}

curl -sX POST http://48.192.170.188:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"Who are you?"}'
# expect: "I'm the Gateway Steward..."
```

Then run `03_test_cases_manual.md`.

---

## Teardown / cost hygiene

```bash
kubectl -n meshops delete svc hello-gateway-iter1-chat
az network nsg rule delete -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-gateway-iter1
az aks stop -n aks-meshops-lab -g rg-meshops-sandbox
```

## Rollback

```bash
helm rollback hello-gateway-iter1 -n meshops
# or
helm uninstall hello-gateway-iter1 -n meshops
```

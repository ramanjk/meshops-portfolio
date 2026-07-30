# Iteration 1 (Read-Only) — Deployment Guide: Shipping the Security Steward

*Audience: Ram, standing up `hello-security-iter1` on the lab AKS cluster. Assumes AKS, ACR, Key Vault, Azure OpenAI, Langfuse, the GitHub token Secret, and the reused `msi-hello-inference` identity already exist.*

Five moves: ensure the GitHub token Secret, build the image, federate Workload Identity, deploy with all values explicit, expose the LoadBalancer through the subnet NSG, verify.

## Prerequisites

| Thing | Value (this lab) |
|---|---|
| Resource group | `rg-meshops-sandbox` |
| AKS cluster | `aks-meshops-lab` (region `southcentralus`) |
| ACR | `acrmeshops` (`acrmeshops.azurecr.io`) |
| Managed identity (reused) | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault | `kv-meshops-3q6qct`, tenant `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Azure OpenAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| GitHub repo | `ramanjk/meshops-portfolio` |
| GitHub token Secret | `github-token` in namespace `meshops`, key `token` |
| Security image | `acrmeshops.azurecr.io/meshops/hello-security:0.1.0` (live digest `sha256:33c999da…`) |

---

## Step 0 — GitHub proposal queue and token

Security reads GitHub open PRs as its substrate:

| Setting | Value |
|---|---|
| Repo | `ramanjk/meshops-portfolio` |
| Steward proposal branch prefix | `hitl/` |
| Read tools | `list_open_proposals`, `get_proposal` |
| Token Secret | `github-token`, key `token` |

The same token is used in Iteration 2 for the bounded label write, but Iteration 1 uses it only for `GET` requests through `github-sec-mcp`.

```bash
kubectl -n meshops get secret github-token
```

---

## Step 1 — Build & push the image

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-security:0.1.0 \
  --image meshops/hello-security:latest .
```

Live image: `acrmeshops.azurecr.io/meshops/hello-security:0.1.0` (digest `sha256:33c999da…`).

---

## Step 2 — Federate Workload Identity to the iter-1 ServiceAccount

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-security-iter1 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-security-iter1 \
  --audience api://AzureADTokenExchange
```

---

## Step 3 — Deploy read-only `hello-security-iter1`

> **GOTCHA:** do **not** use `--reuse-values` on the first install or when changing chart defaults. Pass all keys explicitly so new values (GitHub repo, proposal prefix, write flags) do not silently stay empty.

```bash
helm upgrade --install hello-security-iter1 helm/security -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-security \
  --set image.tag=0.1.0 \
  --set serviceAccount.name=hello-security-iter1 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set github.repo=ramanjk/meshops-portfolio \
  --set github.proposalBranchPrefix=hitl/ \
  --set writeEnabled=false

kubectl -n meshops rollout status deploy/hello-security-iter1 --timeout=150s
```

There is no `write-rbac.yaml` to render. Security's read substrate is GitHub, not Kubernetes.

---

## Step 4 — Public LoadBalancer access + subnet NSG rule

The live iter-1 Service is exposed at `172.206.149.75:8080`.

```bash
kubectl -n meshops get svc hello-security-iter1-chat

az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-security-iter1 --priority 600 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes 172.206.149.75 --destination-port-ranges 8080
```

> **Security:** the chat endpoint has no auth. Narrow `chat.service.loadBalancerSourceRanges` and the NSG source prefix for anything beyond a lab demo.

---

## Step 5 — Verify

```bash
kubectl -n meshops get pods -l app.kubernetes.io/name=hello-security-iter1
# expect: 1/1 Running

curl -s http://172.206.149.75:8080/healthz
# expect: {"status":"ok"}

curl -sX POST http://172.206.149.75:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"Who are you?"}'
# expect: "I'm the Security Steward..."
```

Then run `03_test_cases_manual.md`.

---

## Teardown / cost hygiene

```bash
kubectl -n meshops delete svc hello-security-iter1-chat
az network nsg rule delete -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-security-iter1
az aks stop -n aks-meshops-lab -g rg-meshops-sandbox
```

## Rollback

```bash
helm rollback hello-security-iter1 -n meshops
# or
helm uninstall hello-security-iter1 -n meshops
```

# Iteration 2 (Gated Write + HITL) — Deployment Guide (Gateway)

*Audience: Ram (builder). This deploys `hello-gateway-iter2` with the GitHub-PR approval channel and the safe LiteLLM per-route budget-cap target.*

## 0. Prerequisites

| Thing | Value |
|---|---|
| Chat endpoint | `http://20.188.72.89:8080/` |
| Image | `acrmeshops.azurecr.io/meshops/hello-gateway:0.1.0` |
| Namespace | steward in `meshops`; write target in `meshops-workloads` |
| UAMI | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault / tenant | `kv-meshops-3q6qct` / `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| AOAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| LiteLLM base URL | `http://litellm.meshops-workloads.svc.cluster.local:4000` |
| LiteLLM config | ConfigMap `litellm-config`, key `config.yaml`, namespace `meshops-workloads` |
| Budget targets | `chat-premium,chat-economy`, range `$0..$200` |
| GitHub repo | `ramanjk/meshops-portfolio` |
| GitHub token Secret | `github-token` in namespace `meshops`, key `token` |

The image already includes `gh 2.65.0`, `kubectl`, and the in-repo `litellm_mcp` shim.

---

## 1. Confirm the LiteLLM substrate baseline

```bash
kubectl -n meshops-workloads get svc litellm
kubectl -n meshops-workloads get configmap litellm-config -o jsonpath='{.data.config\.yaml}'
kubectl -n meshops-workloads rollout status deploy/litellm --timeout=120s
```

Baseline routes:

| Route | Upstream | Budget cap |
|---|---|---|
| `chat-premium` | `azure/gpt-4.1` | `50.0` |
| `chat-economy` | `azure/gpt-4.1` | `5.0` |

AOAI auth is keyless: the AOAI resource has `disableLocalAuth=true`, and LiteLLM uses Workload Identity / Entra ID via `enable_azure_ad_token_refresh`.

---

## 2. Build & push the image (if not already present)

```bash
az acr build --registry acrmeshops   --image meshops/hello-gateway:0.1.0   --image meshops/hello-gateway:latest .
```

---

## 3. Workload Identity federated credential for iter-2

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox   --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-gateway-iter2   --identity-name msi-hello-inference -g rg-meshops-sandbox   --issuer "$ISSUER"   --subject system:serviceaccount:meshops:hello-gateway-iter2   --audience api://AzureADTokenExchange
```

---

## 4. Deploy `hello-gateway-iter2` with gated write

> **GOTCHA:** do **not** use `--reuse-values` on first install. Pass all keys explicitly.

```bash
helm upgrade --install hello-gateway-iter2 helm/gateway -n meshops   --set image.repository=acrmeshops.azurecr.io/meshops/hello-gateway   --set image.tag=0.1.0   --set serviceAccount.name=hello-gateway-iter2   --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c   --set keyVault.name=kv-meshops-3q6qct   --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3   --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/   --set env.azureOpenAiChatDeploymentName=gpt-4.1   --set litellm.baseUrl=http://litellm.meshops-workloads.svc.cluster.local:4000   --set writeEnabled=true   --set writeApprovalChannel=github_pr   --set github.repo=ramanjk/meshops-portfolio   --set github.baseBranch=main   --set github.proposalsDir=hitl-proposals   --set github.pollSeconds=20   --set writeNamespace=meshops-workloads   --set budget.allowedRoutes=chat-premium\,chat-economy   --set budget.minBudget=0   --set budget.maxBudget=200

kubectl -n meshops rollout status deploy/hello-gateway-iter2 --timeout=150s
```

What this turns on:

1. `WRITE_ENABLED=true` and gated-write persona.
2. `propose_budget` bound to routes `chat-premium,chat-economy`, range `$0..$200`.
3. GitHub PR channel env (`GITHUB_*`, `GH_TOKEN`) and poll loop every `20s`.
4. Namespaced writer Role/RoleBinding in `meshops-workloads`.

---

## 5. Verify the gate is armed

```bash
kubectl -n meshops logs deploy/hello-gateway-iter2 | grep -E 'WRITE-ENABLED|poll'
# expect:
# [chat] WRITE-ENABLED: HITL gate armed for LiteLLM route budget in ns/meshops-workloads via 'github_pr' channel
# approval poll loop started (every 20s)

curl -s http://20.188.72.89:8080/healthz
# {"status":"ok"}
```

Live proof captured: both iter-2 pods were `1/1`, startup log showed the HITL gate armed, poll loop every 20s, and `gh auth` resolved as `ramanjk`.

---

## 6. Expose the chat UI + NSG rule

```bash
kubectl -n meshops get svc hello-gateway-iter2-chat

az network nsg rule create -g rg-meshops-sandbox   --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus   --name allow-gateway-iter2 --priority 590   --access Allow --direction Inbound --protocol Tcp   --source-address-prefixes Internet --source-port-ranges '*'   --destination-address-prefixes 20.188.72.89 --destination-port-ranges 8080
```

---

## 7. Smoke test the gate

Run [`03_test_cases_manual.md`](03_test_cases_manual.md). Minimum smoke:

1. Ask `Raise chat-economy budget to $12`.
2. Confirm proposal `pw_aec4896a`, preview `5.0 -> $12.00`, PR #15, no change.
3. Merge PR.
4. Confirm `litellm-config` changes `chat-economy` to `12.0`, the LiteLLM Deployment rolls, and audit records execution.
5. Reset to baseline `5.0`.

---

## 8. Roll back to read-only

```bash
helm upgrade hello-gateway-iter2 helm/gateway -n meshops --reuse-values --set writeEnabled=false
```

This removes `WRITE_ENABLED`/`GITHUB_*` on the next rollout and reloads the read-only persona. Or uninstall:

```bash
helm uninstall hello-gateway-iter2 -n meshops
```

---

## 9. Cost hygiene

```bash
kubectl -n meshops delete svc hello-gateway-iter2-chat
az network nsg rule delete -g rg-meshops-sandbox   --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus   --name allow-gateway-iter2
az aks stop --name aks-meshops-lab --resource-group rg-meshops-sandbox
```

## Notes / caveats

- Approver identity is the PR merger's GitHub login (`ramanjk` in the captured run).
- TTL is auto-bumped to at least 7 days for the async PR channel.
- The live captured approve round-trip used PR #15 and proposal `pw_aec4896a`.
- Live spend is not part of this steward until the LiteLLM proxy has a connected Postgres DB.

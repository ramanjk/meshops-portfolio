# Iteration 2 (Gated Write + HITL) — Deployment Guide (SRE)

*Audience: Ram (builder). This deploys `hello-sre-iter2` with the GitHub-PR approval channel and the safe `demo-web` Deployment scale target.*

## 0. Prerequisites

| Thing | Value |
|---|---|
| Chat endpoint | `http://20.94.174.157:8080/` |
| Image | `acrmeshops.azurecr.io/meshops/hello-sre:0.1.0` |
| Namespace | steward in `meshops`; write target in `meshops-workloads` |
| UAMI | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault / tenant | `kv-meshops-3q6qct` / `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| AOAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| AKS resource id | `/subscriptions/d8f26eb0-452d-42ff-89a3-8290f00e132a/resourceGroups/rg-meshops-sandbox/providers/Microsoft.ContainerService/managedClusters/aks-meshops-lab` |
| Prom query URL | `https://amw-meshops-lab-hnfbd3dfb4g6f6gw.southcentralus.prometheus.monitor.azure.com` |
| GitHub repo | `ramanjk/meshops-portfolio` |
| GitHub token Secret | `github-token` in namespace `meshops`, key `token` |

The image already includes `gh 2.65.0`, `kubectl`, and `aks-mcp`.

---

## 1. Apply the safe scale target

```bash
kubectl apply -f helm/sre/extras/demo-workload.yaml
kubectl -n meshops-workloads rollout status deploy/demo-web --timeout=120s
kubectl -n meshops-workloads scale deployment/demo-web --replicas=1
```

`demo-web` is the only allowlisted Deployment for the live demo.

---

## 2. Build & push the image (if not already present)

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-sre:0.1.0 \
  --image meshops/hello-sre:latest .
```

---

## 3. Workload Identity federated credential for iter-2

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-sre-iter2 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-sre-iter2 \
  --audience api://AzureADTokenExchange
```

Live issuer: `https://southcentralus.oic.prod-aks.azure.com/16b3c013-d300-468d-ac64-7eda0820b6d3/b1af5beb-9ed5-421c-ac7e-60a967a15f11/`.

---

## 4. Deploy `hello-sre-iter2` with gated write

> **GOTCHA:** do **not** use `--reuse-values` on first install. Pass all keys explicitly.

```bash
helm upgrade --install hello-sre-iter2 helm/sre -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-sre \
  --set image.tag=0.1.0 \
  --set serviceAccount.name=hello-sre-iter2 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set env.aksResourceId=/subscriptions/d8f26eb0-452d-42ff-89a3-8290f00e132a/resourceGroups/rg-meshops-sandbox/providers/Microsoft.ContainerService/managedClusters/aks-meshops-lab \
  --set env.azureMonitorWorkspaceQueryUrl=https://amw-meshops-lab-hnfbd3dfb4g6f6gw.southcentralus.prometheus.monitor.azure.com \
  --set writeEnabled=true \
  --set writeApprovalChannel=github_pr \
  --set github.repo=ramanjk/meshops-portfolio \
  --set github.baseBranch=main \
  --set github.proposalsDir=hitl-proposals \
  --set github.pollSeconds=20 \
  --set writeNamespace=meshops-workloads \
  --set scale.allowedDeployments=demo-web \
  --set scale.minReplicas=0 \
  --set scale.maxReplicas=5

kubectl -n meshops rollout status deploy/hello-sre-iter2 --timeout=150s
```

What this turns on:

1. `WRITE_ENABLED=true` and gated-write persona.
2. `propose_scale` bound to namespace `meshops-workloads`, allowlist `demo-web`, range `0..5`.
3. GitHub PR channel env (`GITHUB_*`, `GH_TOKEN`) and poll loop every `20s`.
4. Namespaced writer Role/RoleBinding in `meshops-workloads`.

---

## 5. Verify the gate is armed

```bash
kubectl -n meshops logs deploy/hello-sre-iter2 | grep -E 'WRITE-ENABLED|poll'
# expect:
# [chat] WRITE-ENABLED: HITL gate armed for Deployment scale in ns/meshops-workloads via 'github_pr' channel
# approval poll loop started (every 20s)

curl -s http://20.94.174.157:8080/healthz
# {"status":"ok"}
```

---

## 6. Expose the chat UI + NSG rule

```bash
kubectl -n meshops get svc hello-sre-iter2-chat

az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-sre-iter2 --priority 570 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes 20.94.174.157 --destination-port-ranges 8080
```

---

## 7. Smoke test the gate

Run [`03_test_cases_manual.md`](03_test_cases_manual.md). Minimum smoke:

1. Ask `Scale demo-web to 3`.
2. Confirm proposal `pw_…`, preview `1 -> 3`, PR link, no change.
3. Merge PR.
4. Confirm `demo-web` becomes `3/3` ready and audit records execution.
5. Reset:

```bash
kubectl -n meshops-workloads scale deployment/demo-web --replicas=1
```

---

## 8. Roll back to read-only

```bash
helm upgrade hello-sre-iter2 helm/sre -n meshops --reuse-values --set writeEnabled=false
```

This removes `WRITE_ENABLED`/`GITHUB_*` on the next rollout and reloads the read-only persona. Or uninstall:

```bash
helm uninstall hello-sre-iter2 -n meshops
```

---

## 9. Cost hygiene

```bash
kubectl -n meshops delete svc hello-sre-iter2-chat
az network nsg rule delete -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-sre-iter2
az aks stop --name aks-meshops-lab --resource-group rg-meshops-sandbox
```

## Notes / caveats

- Approver identity is the PR merger's GitHub login (`ramanjk` in the captured run).
- TTL is auto-bumped to at least 7 days for the async PR channel.
- The live captured approve round-trip used PR #14 and proposal `pw_98e97111`.
- Re-check rendered writer RBAC before production hardening; see implementation guide note.

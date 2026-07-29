# Iteration 2 (Gated Write + HITL) — Deployment Guide (Quality)

*Audience: Ram (builder). This guide only covers what changes relative to the read-only [`../../iteration-01-read-only/quality/05_deployment_guide.md`](../../iteration-01-read-only/quality/05_deployment_guide.md). The base install (ACR image, Key Vault CSI, Workload Identity, LoadBalancer) is unchanged — reuse it. Enabling gated write is one flag; the GitHub-PR channel adds a token Secret. Like pipeline (and unlike inference), **no RBAC Role is needed** — the write goes to Langfuse over HTTP, bounded by the project credential. It reads almost identically to the [pipeline deployment guide](../pipeline/05_deployment_guide.md).*

## 0. Prerequisite: `gh` in the image (PR channel only)

The single steward `Dockerfile` already bakes `gh` for all stewards; no image change needed. The chat channel needs nothing extra.

## 1. Build & push the iter-2 image

```bash
az acr build -r acrmeshops -t meshops/hello-quality:0.2.0 -t meshops/hello-quality:latest .
```

## 2. (PR channel) Create the GitHub token Secret (shared, once)

```bash
kubectl -n meshops create secret generic github-token --from-literal=token="$GH_PAT"   # repo scope
```

## 3. Deploy `quality-iter2` with gated write

> **GOTCHA:** do **not** use `--reuse-values` on the first install — new chart-default keys (`github.*`) won't merge and the pod CrashLoops. Pass **all** keys explicitly.

```bash
helm upgrade --install quality-iter2 helm/quality -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-quality \
  --set image.tag=0.2.0 \
  --set serviceAccount.name=hello-quality-iter2 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set writeEnabled=true \
  --set writeApprovalChannel=github_pr \
  --set github.repo=ramanjk/meshops-portfolio
```

What `--set writeEnabled=true` turns on:

1. `WRITE_ENABLED=true` (+ TTL + channel) env → the steward loads the **gated-write persona** and mounts `propose_annotation`.
2. The gated-write persona is added to the prompts ConfigMap.
3. With `writeApprovalChannel=github_pr`: `GITHUB_*` env + `GH_TOKEN` (from the `github-token` Secret) + `GH_CONFIG_DIR` are set, and the async PR poll loop starts. The Langfuse write keys (`LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`) are already wired from Key Vault for the read path.

## 3b. Workload-identity federated credential for the new SA

```bash
ISS=$(az aks show -g rg-meshops-sandbox -n aks-meshops-lab --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create --name fic-hello-quality-iter2 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISS" --subject system:serviceaccount:meshops:hello-quality-iter2 \
  --audience api://AzureADTokenExchange
```

## 4. Verify the gate is armed

```bash
kubectl logs -n meshops deploy/hello-quality-iter2 | grep -E 'WRITE-ENABLED|poll'
# -> [chat] WRITE-ENABLED: HITL gate armed for Langfuse annotations via 'github_pr' channel
# -> [chat] approval poll loop started (every 20s)
curl -s -o /dev/null -w '%{http_code}\n' http://<chat-ip>:8080/healthz     # -> 200
```

> **Scheduling note:** the quality pod requests CPU that may exceed current node capacity — on the live deploy it sat `Pending` while the cluster-autoscaler added a system node (3→4), then went `Running`. Give it a few minutes before assuming a failure.

## 5. Expose the chat UI (LoadBalancer) + NSG rule

```bash
IP=$(kubectl get svc -n meshops hello-quality-iter2-chat -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
az network nsg rule create --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus -g rg-meshops-sandbox \
  --name allow-quality-iter2 --priority 550 --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --destination-address-prefixes $IP --destination-port-ranges 8080
```

> **GOTCHA:** if a fresh LB frontend IP returns `000` for > 5 min despite a correct NSG rule (a stuck Azure LB data-path), delete + recreate the Service to get a new IP, then update the rule's destination. (Seen on the pipeline sibling; the quality LB `172.206.134.209` came up cleanly.)

## 6. Smoke test the gate

Run the manual suite ([`03_test_cases_manual.md`](03_test_cases_manual.md)) — at minimum TC-Q1 (merge writes the score), TC-Q2 (close changes nothing). Watch the audit lines:

```bash
kubectl logs -n meshops deploy/hello-quality-iter2 | grep AUDIT
```

## 7. Roll back to read-only

```bash
helm upgrade quality-iter2 helm/quality -n meshops --reuse-values --set writeEnabled=false
```
Drops `WRITE_ENABLED`/`GITHUB_*` and reloads the read-only persona. Or switch to the synchronous chat channel with `--set writeApprovalChannel=chat`. (In the demo, run `quality-iter1` and `quality-iter2` side by side.)

## 8. Cost hygiene

```bash
kubectl -n meshops delete svc hello-quality-iter2-chat
az network nsg rule delete --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus -g rg-meshops-sandbox --name allow-quality-iter2
az aks stop --name aks-meshops-lab --resource-group rg-meshops-sandbox
```

## Notes / caveats

- **Approver identity** is the **PR merger's GitHub login** (github_pr) or `operator (chat)` (chat, no auth yet).
- **Audit** goes to pod logs (`AUDIT …` JSON lines, `kind":"trace-annotation"`); immutable Azure Storage sink (ADR-0011) is a follow-up.
- **Langfuse write credentials:** the applier uses the same project public/secret key pair as the read path — keep it scoped to the one project so the project bound is defence-in-depth.

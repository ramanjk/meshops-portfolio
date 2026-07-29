# Iteration 2 (Gated Write + HITL) — Deployment Guide (Pipeline)

*Audience: Ram (builder). This guide only covers what changes relative to the read-only [`../../iteration-01-read-only/pipeline/05_deployment_guide.md`](../../iteration-01-read-only/pipeline/05_deployment_guide.md). The base install (ACR image, Key Vault CSI, Workload Identity, LoadBalancer) is unchanged — reuse it. Enabling gated write is one flag; the GitHub-PR channel adds a token Secret. Unlike inference, **no RBAC Role is needed** — the write goes to MLflow over HTTP, bounded to one model.*

## 0. Prerequisite: `gh` in the image (PR channel only)

The GitHub-PR channel shells out to the `gh` CLI. The single steward `Dockerfile` already bakes `gh` (pinned via `GH_VERSION`) for **all** stewards, so no image change is needed. The chat channel needs nothing extra.

## 1. Build & push the iter-2 image

```bash
az acr build -r acrmeshops -t meshops/hello-pipeline:0.2.0 -t meshops/hello-pipeline:latest .
```

## 2. (PR channel) Create the GitHub token Secret

```bash
kubectl -n meshops create secret generic github-token --from-literal=token="$GH_PAT"   # repo scope
```
(This Secret is shared with the other gated-write stewards; create it once.)

## 3. Deploy `pipeline-iter2` with gated write

> **GOTCHA (learned the hard way):** do **not** use `helm upgrade --reuse-values` for the first install — it does *not* merge new chart-default keys, so `github.*` render empty and the pod CrashLoops. Pass **all** keys explicitly (as below) on the first install.

```bash
helm upgrade --install pipeline-iter2 helm/pipeline -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-pipeline \
  --set image.tag=0.2.0 \
  --set serviceAccount.name=hello-pipeline-iter2 \
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

1. `WRITE_ENABLED=true` (+ `WRITE_PROPOSAL_TTL_SECONDS`, `WRITE_APPROVAL_CHANNEL`) env → the steward loads the **gated-write persona** and mounts `propose_promotion`.
2. The gated-write persona is added to the prompts ConfigMap.
3. With `writeApprovalChannel=github_pr`: `GITHUB_*` env + `GH_TOKEN` (from the `github-token` Secret) + `GH_CONFIG_DIR` are set, and the async PR poll loop starts.

## 3b. Workload-identity federated credential for the new SA

The chart is parameterized by `serviceAccount.name`, so `iter2` uses a **new** SA (`hello-pipeline-iter2`). Workload-identity federated credentials are pinned to the exact SA subject, so add one on the shared UAMI:

```bash
ISS=$(az aks show -g rg-meshops-sandbox -n aks-meshops-lab --query oidcIssuerProfile.issuerUrl -o tsv)
az identity federated-credential create --name fic-hello-pipeline-iter2 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISS" --subject system:serviceaccount:meshops:hello-pipeline-iter2 \
  --audience api://AzureADTokenExchange
```

## 4. Verify the gate is armed

```bash
kubectl get pods -n meshops -l app.kubernetes.io/name=hello-pipeline-iter2
kubectl logs -n meshops deploy/hello-pipeline-iter2 | grep -E 'WRITE-ENABLED|poll'
# -> [chat] WRITE-ENABLED: HITL gate armed for model 'phi-4-mini-meshops' via 'github_pr' channel
# -> [chat] approval poll loop started (every 20s)
curl -s -o /dev/null -w '%{http_code}\n' http://<chat-ip>:8080/healthz     # -> 200
```

## 5. Expose the chat UI (LoadBalancer) + NSG rule

The chart ships `hello-pipeline-iter2-chat` as a `LoadBalancer`. Add a subnet-NSG inbound rule for its public IP (port 8080):

```bash
IP=$(kubectl get svc -n meshops hello-pipeline-iter2-chat -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
az network nsg rule create --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus -g rg-meshops-sandbox \
  --name allow-pipeline-iter2 --priority 540 --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --destination-address-prefixes $IP --destination-port-ranges 8080
```

> **GOTCHA:** if a freshly-assigned LB frontend IP returns `000` for > 5 min despite a correct NSG rule (a stuck Azure LB data-path), delete and recreate the Service (`kubectl delete svc hello-pipeline-iter2-chat` → `helm upgrade pipeline-iter2 helm/pipeline --reuse-values`) to get a fresh IP, then update the NSG rule's destination. This happened on the live deploy (`74.145.208.52` → `52.249.59.40`).

## 6. Smoke test the gate

Run the manual suite ([`03_test_cases_manual.md`](03_test_cases_manual.md)) — at minimum TC-P1 (merge promotes v3), TC-P2 (close changes nothing). Watch the audit lines:

```bash
kubectl logs -n meshops deploy/hello-pipeline-iter2 | grep AUDIT
```

## 6b. Reset the demo baseline / register a new Staging candidate

A successful promote (TC-P1) **mutates the registry** — v3 moves to Production, so the "should we promote v3?" scenario no longer has a Staging candidate. Two Jobs under `helm/pipeline/extras/` restore or extend the demo state:

```bash
# Full reset → v1 Archived / v2 Production / v3 Staging (nukes + reseeds the model)
kubectl delete job mlflow-seed -n mlflow --ignore-not-found
kubectl apply -f helm/pipeline/extras/mlflow-seed.yaml
kubectl -n mlflow wait --for=condition=complete job/mlflow-seed --timeout=180s
kubectl -n mlflow logs job/mlflow-seed | grep -E 'v[0-9]:'

# OR append a NEW candidate (e.g. v4) to Staging WITHOUT wiping (mirrors training/CI)
kubectl delete job mlflow-add-candidate -n mlflow --ignore-not-found
kubectl apply -f helm/pipeline/extras/mlflow-add-candidate.yaml
kubectl -n mlflow wait --for=condition=complete job/mlflow-add-candidate --timeout=180s
kubectl -n mlflow logs job/mlflow-add-candidate | grep -E '^\[add\]|v[0-9]:'
```

Tune the appended candidate via env on `mlflow-add-candidate.yaml`: `CANDIDATE_ACCURACY` (default `0.88`) and `CANDIDATE_STAGE` (default `Staging`). MLflow assigns the next version number automatically.

> **Separation of concerns:** registering a candidate is a **training/CI** action, deliberately kept *outside* the steward. The Pipeline Steward's gated-write applier is bound only to `transition-stage` on `phi-4-mini-meshops` — it can promote/archive existing versions, never mint new ones. These Jobs stand in for the pipeline that would produce a candidate upstream.

Also clean any HITL audit residue (`hitl-proposals/pw_*.md`) merged onto `main` during testing if you want a pristine repo:

```bash
git rm hitl-proposals/pw_*.md && git commit -m "chore: clean HITL audit residue" && git push
```

## 7. Roll back to read-only

```bash
helm upgrade pipeline-iter2 helm/pipeline -n meshops --reuse-values --set writeEnabled=false
```
This drops `WRITE_ENABLED`/`GITHUB_*` and reloads the read-only persona — back to Iteration-1 behaviour. Or switch to the synchronous chat channel with `--set writeApprovalChannel=chat`. (In the live demo we simply run `pipeline-iter1` and `pipeline-iter2` **side by side** so you can show read-only vs gated-write on two URLs.)

## 8. Cost hygiene

Same as read-only — when done demoing, release the public LB IP and stop the cluster:

```bash
kubectl -n meshops delete svc hello-pipeline-iter2-chat
az network nsg rule delete --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus -g rg-meshops-sandbox --name allow-pipeline-iter2
az aks stop --name aks-meshops-lab --resource-group rg-meshops-sandbox
```

## Notes / caveats

- **Approver identity** is the **PR merger's GitHub login** (github_pr channel — real identity) or `operator (chat)` (chat channel, no auth yet). Do not expose the chat LB with write enabled and the chat channel; the PR channel is safer because approval requires repo write access.
- **Audit** currently goes to pod logs (`AUDIT …` JSON lines, `kind":"registry-promotion"`). The immutable Azure Storage sink (ADR-0011) is a follow-up.
- **MLflow write credentials:** the applier uses whatever auth the tracking URI requires; keep that credential scoped to the one registered model's registry so the single-model bound is defence-in-depth, not the only line.

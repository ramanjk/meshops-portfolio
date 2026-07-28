# Iteration 1 (Read-Only) — Deployment Guide: Shipping the Quality Steward

*Audience: Ram, standing up `hello-quality` on the lab AKS cluster. Assumes the shared lab substrate (AKS, ACR, Key Vault, Azure OpenAI, **Langfuse already in-cluster**, the `msi-hello-inference` managed identity) stood up with the Inference and Pipeline builds is already standing.*

This one is shorter than the Pipeline steward, because the Quality Steward's substrate — the **Langfuse project** — has been running since the Inference steward as the OTel sink. **There is nothing to stand up or seed for the steward to function.** So it's four moves: build the image, wire Workload Identity, deploy, verify. (Then an *optional* fifth: seed eval scores so the drift reasoning has something to chew on.)

> **⚠️ The lab is cost-stopped.** Before anything below, resume the environment. Then re-expose the earlier stewards if you want the side-by-side mesh tests (their old LB IPs `104.44.182.236` / `135.233.240.146` were freed at shutdown and will be reassigned).
>
> ```bash
> az aks start -n aks-meshops-lab -g rg-meshops-sandbox
> az vm start  -n vm-jumpbox-meshops -g rg-meshops-sandbox
> kubectl -n langfuse get pods            # confirm Langfuse came back (PVCs persisted)
> # optional: kubectl apply -f helm/stewards/extras/workspace.yaml  (only if you want Inference live)
> ```

## Prerequisites

| Thing | Value (this lab) |
|---|---|
| Resource group | `rg-meshops-sandbox` |
| AKS cluster | `aks-meshops-lab` (region `southcentralus`) |
| ACR | `acrmeshops` (`acrmeshops.azurecr.io`) |
| Managed identity (reused) | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault | `kv-meshops-3q6qct`, tenant `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| Azure OpenAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| Langfuse (substrate) | in-cluster ns `langfuse`, `http://langfuse-web.langfuse.svc.cluster.local:3000` |

The Quality steward **reuses** the Inference steward's managed identity (it already has Azure OpenAI + Key Vault access), so no new role assignments — just one new federated credential (step 2). The `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` must already exist as Key Vault secrets (they do — the earlier stewards use them for OTel export).

---

## Step 1 — Build & push the image

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-quality:0.0.1 \
  --image meshops/hello-quality:latest .
```

Server-side build (no local Docker). The image bakes all stewards (`hello-inference`, `hello-pipeline`, `hello-quality`) + all MCP shims.

## Step 2 — Federate Workload Identity to the new ServiceAccount

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-quality \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-quality \
  --audience api://AzureADTokenExchange
```

This lets the `hello-quality` ServiceAccount exchange its token for the existing identity — so the pod authenticates to Azure OpenAI and pulls the `LANGFUSE_*` secrets from Key Vault without any stored key.

## Step 3 — Deploy the steward

```bash
helm upgrade --install hello-quality helm/quality -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-quality \
  --set image.tag=0.0.1 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1

kubectl -n meshops rollout status deploy/hello-quality --timeout=150s
```

> The `LANGFUSE_HOST` defaults to the in-cluster service in `settings.py`, so it isn't passed here. Override with `--set env.langfuseHost=...` only if Langfuse moves. `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` arrive via the Key Vault CSI `SecretProviderClass` — no plaintext keys in values.

### Step 3b — Public LoadBalancer access (the subnet-NSG gotcha)

The chat Service is `type: LoadBalancer`. Get its IP:

```bash
kubectl -n meshops get svc hello-quality-chat -w   # wait for EXTERNAL-IP
```

The BYO `snet-aks` subnet has an AKS-auto-created NSG
(`vnet-meshops-lab-snet-aks-nsg-southcentralus`, **not** Terraform-managed) whose
`DenyAllInbound` blocks the public LB even though the node NSG gets the
cloud-provider allow rule. Add an inbound rule for the assigned IP (use a fresh
priority so it doesn't collide with the inference/pipeline rules at 500/510):

```bash
az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  -n allow-quality-chat-lb-inbound --priority 520 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes <EXTERNAL-IP> --destination-port-ranges 8080
```

> **Security:** the endpoint has **no auth**. To restrict it, set
> `chat.service.loadBalancerSourceRanges` in the Helm values and narrow the NSG
> rule's `--source-address-prefixes` to your egress CIDRs.

---

## Step 4 — Verify

```bash
kubectl -n meshops get pods -l app.kubernetes.io/name=hello-quality   # 1/1 Running
kubectl -n meshops logs -l app.kubernetes.io/name=hello-quality | tail
# expect: "persona loaded, MCP tools connected" + WI clientId resolved

curl -s http://<EXTERNAL-IP>:8080/healthz          # {"status":"ok"}
curl -sX POST http://<EXTERNAL-IP>:8080/chat -H 'Content-Type: application/json' \
  -d '{"message":"How many recent traces do you see, and how many carry eval scores?"}'
# expect: a real trace count (there will be traces), likely 0 scored on a fresh
#         lab, + a trace_id. That honest "0 scored" answer is correct.
```

Then walk `03_test_cases_manual.md` for the full prompt suite.

---

## Step 5 (optional) — Seed eval scores so drift reasoning has data

Out of the box the steward will see **traces but no scores**, so P-04 (drift reasoning) will honestly report "no scores to judge from." To make the quality/drift answers rich, write some evaluation scores into Langfuse. Two paths:

- **Quick/manual:** `POST <LANGFUSE_HOST>/api/public/scores` (HTTP Basic pk:sk) with a `traceId`, a `name` (e.g. `faithfulness`), a numeric `value` in `[0,1]`, and `dataType: "NUMERIC"`. Do this for a handful of recent traces.
- **Realistic (future iteration):** run a **Ragas / Promptfoo / Foundry** eval job that scores a batch of traces and posts the results back to Langfuse. This is the same eval suite the full Quality loop (agent-catalog §5) eventually runs itself.

> Note this is a **prerequisite for meaningful observations, not for the steward to run** — the read-only slice works with zero scores; it just reports the honest "nothing to score yet" state.

---

## Teardown (billing hygiene)

The steward pod and its public LB accrue cost; Langfuse is shared infrastructure that was already running.

```bash
# Free the public LB IP:
kubectl -n meshops delete svc hello-quality-chat

# Full stop for the day (compute):
az aks stop -n aks-meshops-lab -g rg-meshops-sandbox
az vm deallocate -n vm-jumpbox-meshops -g rg-meshops-sandbox
```

Notes:
- The `allow-quality-chat-lb-inbound` NSG rule persists but is harmless (nothing listens once the Service is gone).
- **Do not** delete the `langfuse` namespace as "teardown" — it's the shared substrate for all stewards and its PVCs hold every steward's trace history.
- To remove the steward entirely: `helm uninstall hello-quality -n meshops` (leaves Langfuse intact).

## Rollback

```bash
helm rollback hello-quality -n meshops    # previous revision
# or
helm uninstall hello-quality -n meshops   # remove the steward (leaves Langfuse intact)
```

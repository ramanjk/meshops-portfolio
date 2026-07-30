# Iteration 2 (Gated Write + HITL) — Deployment Guide (Security)

*Audience: Ram (builder). This deploys `hello-security-iter2` with the chat approval channel and the safe GitHub PR-quarantine target.*

## 0. Prerequisites

| Thing | Value |
|---|---|
| Chat endpoint | `http://172.202.188.183:8080/` |
| Image | `acrmeshops.azurecr.io/meshops/hello-security:0.1.0` (digest `sha256:33c999da…`) |
| Namespace | `meshops` |
| UAMI | `msi-hello-inference`, clientId `a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c` |
| Key Vault / tenant | `kv-meshops-3q6qct` / `16b3c013-d300-468d-ac64-7eda0820b6d3` |
| AOAI | `https://aoai-meshops-99281a.openai.azure.com/`, deployment `gpt-4.1` |
| GitHub repo | `ramanjk/meshops-portfolio` |
| GitHub token Secret | `github-token` in namespace `meshops`, key `token` |
| Proposal prefix | `hitl/` |
| Quarantine labels | `quarantined,security-hold` |
| Approval channel | `chat` |

The image includes the in-repo `github_sec_mcp` shim. Security does not need `kubectl` authority for its write path because the one mutation is a GitHub label add.

---

## 1. Confirm the GitHub token Secret

```bash
kubectl -n meshops get secret github-token
```

This Secret is required in both iterations. Iteration 2 uses it to read open PRs and, after approval, apply one allow-listed label.

---

## 2. Build & push the image (if not already present)

```bash
az acr build --registry acrmeshops \
  --image meshops/hello-security:0.1.0 \
  --image meshops/hello-security:latest .
```

Live image: `acrmeshops.azurecr.io/meshops/hello-security:0.1.0` (digest `sha256:33c999da…`).

---

## 3. Workload Identity federated credential for iter-2

```bash
ISSUER=$(az aks show -n aks-meshops-lab -g rg-meshops-sandbox \
  --query oidcIssuerProfile.issuerUrl -o tsv)

az identity federated-credential create --name fic-hello-security-iter2 \
  --identity-name msi-hello-inference -g rg-meshops-sandbox \
  --issuer "$ISSUER" \
  --subject system:serviceaccount:meshops:hello-security-iter2 \
  --audience api://AzureADTokenExchange
```

---

## 4. Deploy `hello-security-iter2` with gated write

> **GOTCHA:** do **not** use `--reuse-values` on first install. Pass all keys explicitly.
>
> **Comma gotcha:** escape the comma in `quarantine.allowedLabels`, or quote the whole `--set` expression exactly as shown.

```bash
helm upgrade --install hello-security-iter2 helm/security -n meshops \
  --set image.repository=acrmeshops.azurecr.io/meshops/hello-security \
  --set image.tag=0.1.0 \
  --set serviceAccount.name=hello-security-iter2 \
  --set serviceAccount.clientId=a6fb9f44-93e2-46bc-b5ed-1ab779d26a4c \
  --set keyVault.name=kv-meshops-3q6qct \
  --set keyVault.tenantId=16b3c013-d300-468d-ac64-7eda0820b6d3 \
  --set env.azureOpenAiEndpoint=https://aoai-meshops-99281a.openai.azure.com/ \
  --set env.azureOpenAiChatDeploymentName=gpt-4.1 \
  --set github.repo=ramanjk/meshops-portfolio \
  --set github.proposalBranchPrefix=hitl/ \
  --set writeEnabled=true \
  --set writeApprovalChannel=chat \
  --set 'quarantine.allowedLabels=quarantined\,security-hold'

kubectl -n meshops rollout status deploy/hello-security-iter2 --timeout=150s
```

What this turns on:

1. `WRITE_ENABLED=true` and gated-write persona.
2. `propose_quarantine` bound to labels `quarantined,security-hold`.
3. Chat approval channel (`POST /approve` / `POST /reject`).
4. No Kubernetes writer Role. The write target is GitHub only.

---

## 5. Verify the gate is armed

```bash
kubectl -n meshops logs deploy/hello-security-iter2 | grep 'WRITE-ENABLED'
# expect:
# [chat] WRITE-ENABLED: HITL gate armed for PR quarantine in ramanjk/meshops-portfolio via 'chat' channel

curl -s http://172.202.188.183:8080/healthz
# {"status":"ok"}
```

Live proof captured: startup log showed exactly:

```text
[chat] WRITE-ENABLED: HITL gate armed for PR quarantine in ramanjk/meshops-portfolio via 'chat' channel
```

---

## 6. Expose the chat UI + NSG rule

```bash
kubectl -n meshops get svc hello-security-iter2-chat

az network nsg rule create -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-security-iter2 --priority 610 \
  --access Allow --direction Inbound --protocol Tcp \
  --source-address-prefixes Internet --source-port-ranges '*' \
  --destination-address-prefixes 172.202.188.183 --destination-port-ranges 8080
```

> **Security:** the chat endpoint has no auth. Narrow `chat.service.loadBalancerSourceRanges` and the NSG source prefix for anything beyond a lab demo.

---

## 7. Prove there is no cluster write power

```bash
kubectl auth can-i create pods \
  --as system:serviceaccount:meshops:hello-security-iter2 -A
kubectl auth can-i patch configmaps \
  --as system:serviceaccount:meshops:hello-security-iter2 -A
kubectl auth can-i patch deployments \
  --as system:serviceaccount:meshops:hello-security-iter2 -A
kubectl auth can-i list secrets \
  --as system:serviceaccount:meshops:hello-security-iter2 -A
# expect: no / no / no / no
```

Live proof captured: all four returned `no`.

---

## 8. Smoke test the gate

Run [`03_test_cases_manual.md`](03_test_cases_manual.md). Minimum smoke:

1. Use a suspicious test PR like PR #16 with the injection payload.
2. Ask the steward to inspect and quarantine it.
3. Confirm proposal `pw_571b7111`, preview, and PENDING status; no label yet.
4. POST `/approve`.
5. Confirm `quarantined` label and audit comment on the PR.
6. Try non-allowlisted `malware-flag`; confirm refusal/denial.
7. Cleanup: close PR #16, delete branch, confirm `0` open PRs.

---

## 9. Optional `github_pr` channel

The chart still supports the shared async channel. If chosen, add the GitHub PR settings and keep the same label allowlist:

```bash
helm upgrade hello-security-iter2 helm/security -n meshops --reuse-values \
  --set writeApprovalChannel=github_pr \
  --set github.baseBranch=main \
  --set github.proposalsDir=hitl-proposals \
  --set github.pollSeconds=20
```

The live Security deployment defaults to `chat` because a PR-to-approve-a-PR-quarantine is recursive/confusing and chat is synchronously demoable.

---

## 10. Roll back to read-only

```bash
helm upgrade hello-security-iter2 helm/security -n meshops --reuse-values --set writeEnabled=false
```

This removes `WRITE_ENABLED` and reloads the read-only persona. Or uninstall:

```bash
helm uninstall hello-security-iter2 -n meshops
```

---

## 11. Cost hygiene

```bash
kubectl -n meshops delete svc hello-security-iter2-chat
az network nsg rule delete -g rg-meshops-sandbox \
  --nsg-name vnet-meshops-lab-snet-aks-nsg-southcentralus \
  --name allow-security-iter2
az aks stop --name aks-meshops-lab --resource-group rg-meshops-sandbox
```

## Notes / caveats

- Approval identity is `operator` for the live chat channel.
- `github_pr` remains supported via the shared spine but is not the default.
- The only live write is an allow-listed GitHub label add plus best-effort audit comment.
- The chart creates no Kubernetes writer RBAC Role.

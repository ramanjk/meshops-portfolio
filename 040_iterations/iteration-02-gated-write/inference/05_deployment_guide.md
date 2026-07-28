# Iteration 2 (Gated Write + HITL) — Deployment Guide

*Audience: Ram (builder). This guide only covers what changes relative to the read-only [`../../iteration-01-read-only/inference/05_deployment_guide.md`](../../iteration-01-read-only/inference/05_deployment_guide.md). The base install (ACR image, Key Vault CSI, Workload Identity, LoadBalancer) is unchanged — reuse it. Enabling gated write is one flag plus a bounded RBAC Role that Helm creates for you.*

## 0. Prerequisite: kubectl in the image

The deterministic executor shells out to `kubectl`. The steward image already ships `kubectl` for aks-mcp's `kubectl` component, so no image change is needed. If you build a slimmer image, ensure `kubectl` is on `PATH` (or set `KUBECTL_BINARY`).

## 1. Enable gated write

```bash
# Rebuild/push the image if code changed (same as read-only):
#   az acr build -r $ACR -t meshops/hello-inference:0.1.0 .

helm upgrade --install hello-inference helm/stewards \
  --namespace meshops \
  --set image.repository=$ACR_LOGIN_SERVER/meshops/hello-inference \
  --set image.tag=0.1.0 \
  --set writeEnabled=true \
  --set writeNamespace=meshops-workloads \
  # ... plus the same value overrides you already use (endpoints, clientId, KV) ...
```

What `--set writeEnabled=true` turns on:

1. `WRITE_ENABLED=true` + `WRITE_NAMESPACE` env on the Deployment → the steward loads the **gated-write persona** and mounts `propose_write`.
2. The gated-write persona is added to the prompts ConfigMap.
3. **`helm/stewards/templates/write-rbac.yaml`** creates a namespaced `Role`/`RoleBinding` **`hello-inference-writer`** in `meshops-workloads`.

## 2. Verify the write-but-bounded RBAC

```bash
kubectl get role,rolebinding -n meshops-workloads | grep hello-inference-writer

# The SA CAN create a pod in the write namespace:
kubectl auth can-i create pods \
  --as=system:serviceaccount:meshops:hello-inference -n meshops-workloads      # -> yes

# The SA CANNOT touch secrets, rbac, or cluster-scoped resources:
kubectl auth can-i get secrets \
  --as=system:serviceaccount:meshops:hello-inference -n meshops-workloads      # -> no
kubectl auth can-i create clusterrolebindings \
  --as=system:serviceaccount:meshops:hello-inference                            # -> no
kubectl auth can-i delete pods \
  --as=system:serviceaccount:meshops:hello-inference -n kube-system             # -> no
```

If any of the "no" checks returns "yes", **stop** — the backstop is misconfigured (do not rely on the app-level namespace check alone).

## 3. Smoke test the gate

Open the chat UI and run the manual suite ([`03_test_cases_manual.md`](03_test_cases_manual.md)) — at minimum TC-W1 (approve creates a pod), TC-W2 (reject changes nothing), and TC-W4 (approved Secret write is denied by RBAC). Watch the pod logs for `AUDIT` lines:

```bash
kubectl logs -n meshops deploy/hello-inference | grep AUDIT
```

## 4. Roll back to read-only

Gated write is a flag, so rolling back is one command — no data migration:

```bash
helm upgrade hello-inference helm/stewards --namespace meshops --reuse-values \
  --set writeEnabled=false
```

This removes the `writer` Role/RoleBinding, drops `WRITE_ENABLED`, and reloads the read-only persona. The steward returns to its Iteration-1 behaviour.

## 4b. (Optional) Use the GitHub-PR approval channel

Instead of the synchronous chat card, the steward can open a **PR per proposal** — **merge = approve, close = reject** (ADR-0011). The write is still applied in-process by the steward's bounded executor; the PR is only the approval signal and human-readable audit artifact.

```bash
# 1. Give the pod a GitHub PAT (repo scope) for the gh CLI:
kubectl -n meshops create secret generic github-token --from-literal=token="$GH_PAT"

# 2. Enable write + select the PR channel:
helm upgrade hello-inference helm/stewards --namespace meshops --reuse-values \
  --set writeEnabled=true \
  --set writeApprovalChannel=github_pr \
  --set github.repo=ramanjk/meshops-portfolio \
  --set github.baseBranch=main \
  --set github.proposalsDir=hitl-proposals \
  --set github.pollSeconds=20
```

What this changes vs the chat channel:

1. `WRITE_APPROVAL_CHANNEL=github_pr` + `GITHUB_*` env + `GH_TOKEN` (from the `github-token` Secret) are set on the Deployment.
2. On each proposal the steward creates branch `hitl/pw_…`, commits `hitl-proposals/pw_….md` (body = dry-run preview + proposal JSON), and opens a PR; the chat card shows a **"Review PR"** link instead of Approve/Reject buttons.
3. A background poll loop (`github.pollSeconds`) reconciles PR state into gate decisions; you can force it with `curl -XPOST http://<chat>/reconcile`.
4. The proposal TTL is auto-extended to ≥ 7 days so an async review never expires the proposal mid-flight.

Run manual **TC-W8** to validate the full merge→create / close→reject flow. Roll back to the chat channel with `--set writeApprovalChannel=chat` (or to read-only with `--set writeEnabled=false`).

## 5. Cost hygiene (unchanged)

Same as read-only — when done demoing:

```bash
kubectl -n meshops delete svc hello-inference-chat   # release the public LB IP
az aks stop --name aks-meshops-lab --resource-group <rg>
```

## Notes / caveats

- **Approver identity** is recorded as `operator (chat)` — the interactive channel has no auth yet. Do not expose the chat LoadBalancer to the internet with write enabled; restrict `chat.service.loadBalancerSourceRanges` to your egress IPs. On the **GitHub-PR channel** the approver is recorded as the **PR merger's GitHub login** (real identity).
- **Audit** currently goes to pod logs (`AUDIT …` JSON lines). The immutable Azure Storage sink (ADR-0011) is a follow-up; until then, ship pod logs to a retained log store if you need durable audit.
- **KAITO workspace scaling** is a `patch` on `spec.resource.count` (operation `patch`), not `kubectl scale`; the gate supports both `patch` and `scale`.

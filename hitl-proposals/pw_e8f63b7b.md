# HITL write proposal `pw_e8f63b7b`

**Intent:** create Pod in ns/meshops-workloads

**Rationale:** Create a minimal test pod for diagnostics in the meshops-workloads namespace, with automatic cleanup and diagnostic labeling.

> Merging this PR **approves** the write; closing it **rejects** it. The steward's deterministic executor applies it under a namespaced, write-but-bounded ServiceAccount (ADR-0011).

## Server dry-run preview

```
pod/test-pod-diag-01
```

## Proposal

```json
{
  "operation": "create",
  "resource_kind": "Pod",
  "namespace": "meshops-workloads",
  "name": null,
  "manifest": {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
      "name": "test-pod-diag-01",
      "labels": {
        "meshops.io/ephemeral": "true"
      }
    },
    "spec": {
      "containers": [
        {
          "name": "busybox",
          "image": "busybox",
          "command": [
            "sleep",
            "300"
          ]
        }
      ],
      "activeDeadlineSeconds": 600
    }
  },
  "patch": null,
  "replicas": null
}
```

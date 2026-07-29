# HITL write proposal `pw_ee7f0bff`

**Intent:** patch Workspace/lab-phi-4-mini-eus2-01 in ns/meshops-workloads

**Rationale:** Scaling to 2 replicas to increase inference throughput as requested.

> Merging this PR **approves** the write; closing it **rejects** it. The steward's deterministic executor applies it under a namespaced, write-but-bounded ServiceAccount (ADR-0011).

## Server dry-run preview

```
(dry-run failed) Error from server (BadRequest): admission webhook "validation.workspace.kaito.sh" denied the request: validation failed: field is immutable: resource.count
```

## Proposal

```json
{
  "operation": "patch",
  "resource_kind": "Workspace",
  "namespace": "meshops-workloads",
  "name": "lab-phi-4-mini-eus2-01",
  "manifest": null,
  "patch": {
    "resource": {
      "count": 2
    }
  },
  "replicas": null
}
```

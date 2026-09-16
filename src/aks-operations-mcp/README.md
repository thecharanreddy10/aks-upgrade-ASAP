# AKS Operations MCP (Phase 2)

This project exposes AKS operational checks as MCP tools over MCP HTTP transports. It is the MCP server component of the **AKS Upgrade Agent** POC — see the [repository root README](../../README.md) for the full architecture, end-to-end workflow, safety model, and validation results.

In Phase 4, it also includes an Azure Functions entrypoint (`function_app.py`) at `/api/mcp` for remote hosting/deployment.

## Role in the AKS Upgrade Agent POC

The Foundry Agent consumes this MCP server's tools through a Foundry Toolbox. Tools fall into two categories:

- **Read-only assessment/discovery tools** — cluster/node-pool discovery, Azure upgrade-profile lookups, mandatory readiness checks (node/pod/PDB/storage health, deprecated API checks), and advisory optional checks.
- **Explicit write/upgrade tools** — the asynchronous upgrade coordinator and node/pod/PDB/storage/deprecated-API remediation tools, all gated behind explicit confirmation and write-enable flags (see [Upgrade guardrails](#upgrade-guardrails) and [Remediation guardrails](#remediation-guardrails) below).

## Implemented tools

- `aks_get_cluster_details`
- `aks_get_node_pools`
- `aks_get_available_upgrades`
- `aks_check_node_health`
- `aks_check_pod_health`
- `aks_check_pdb`
- `aks_check_storage`
- `aks_check_deprecated_apis`
- `aks_validate_upgrade_readiness`
- `aks_execute_confirmed_upgrade`
- `aks_get_upgrade_execution_status`
- `aks_upgrade_node_pool`
- `aks_remediate_pdb`
- `aks_remediate_pods`
- `aks_remediate_node`
- `aks_remediate_storage`
- `aks_remediate_deprecated_apis`
- `aks_generate_deprecated_api_manifests`

`aks_check_node_health`, `aks_check_pod_health`, `aks_check_pdb`, `aks_check_storage`, and `aks_check_deprecated_apis` back the **mandatory** upgrade-readiness checks. Optional/advisory upgrade-smoothness validations (single-replica services, operator health, node-pool surge, PriorityClass) are agent-side conversational checks layered on top of these tools and are never treated as automatic upgrade blockers.

## Upgrade guardrails

`aks_execute_confirmed_upgrade` is the non-blocking upgrade coordinator exposed to the agent. It is intended for long-running AKS control-plane and node-pool upgrades:

1. The calling agent must obtain explicit human approval for the specific upgrade plan before invoking it.
2. It runs the existing authoritative target and mandatory readiness checks before submitting a control-plane write.
3. It submits at most one Azure long-running upgrade operation per call and returns without waiting for the Azure operation to finish.
4. The agent should use `aks_get_upgrade_execution_status` to observe the live provisioning/version state before advancing the workflow.
5. Once the current stage has reached its target version and `Succeeded` provisioning state, the agent can call `aks_execute_confirmed_upgrade` again with the same target and scope to advance to the next stage.
6. When a completed control-plane or node-pool stage is observed, the coordinator runs read-only post-upgrade smoke checks and returns them in `post_upgrade_smoke_checks`.
7. For `complete_cluster`, node-pool upgrade evidence is refreshed only after the control-plane target is observed. A node pool is modified only when fresh Azure evidence shows the target path is `SUPPORTED`.
8. If a control-plane or node-pool operation is already in progress, the coordinator returns an `in_progress` state and does not submit a duplicate write.
9. The coordinator returns `completed`, `partial`, `blocked`, or `failed` states rather than holding the MCP request open for the full Azure long-running operation.

In-progress tracking uses a **process-local** lock (an in-memory `threading.Lock` keyed by cluster/pool). It prevents duplicate submissions from the same MCP process, but it is **not** a distributed lock and does not coordinate across multiple MCP server replicas. `Failed`/`Canceled` terminal states are reported as-is; the coordinator does not perform speculative automatic retries.

Real upgrade writes still require:

- `AKS_UPGRADE_ENABLE_WRITE=true`.
- `check_mode=full`.
- The MCP runtime identity must have sufficient Azure authorization for the requested operation.

Optional env var:

- `AKS_UPGRADE_ENABLE_WRITE` (default: `false`)

`aks_upgrade_node_pool` remains available for compatibility but is not the preferred agent workflow. The agent should use `aks_execute_confirmed_upgrade` for confirmed upgrade execution and `aks_get_upgrade_execution_status` for progress checks.

## Remediation guardrails

Remediation tools that modify cluster resources default to `dry_run=true` and `check_mode="full"`.

Real remediation writes require:

1. `dry_run=false` explicitly from the caller/agent.
2. `check_mode=full`.
3. `AKS_REMEDIATION_ENABLE_WRITE=true` on the MCP server.
4. The MCP runtime identity must have sufficient Azure/AKS/Kubernetes authorization for the requested operation.
5. Protected cluster-critical namespaces remain blocked.
6. Destructive remediations require their explicit destructive-operation confirmation flag.

There is no application-level approval token for upgrade or remediation operations. The LLM/agent does not receive or provide a secret token. The security boundary is the explicit write-enable setting, remediation-specific confirmation for destructive actions, and the runtime identity's Azure/Kubernetes permissions. Explicit human approval for upgrades is enforced at the agent/instruction level, not by a cryptographic token issued or validated here.

## Local run

```bash
pip install -r requirements.txt
python main.py
```

## Function-hosted MCP validation

Once deployed to Azure Functions, validate the endpoint:

```bash
curl -X POST "https://<function-app-name>.azurewebsites.net/api/mcp" \\
	-H "Content-Type: application/json" \\
	-d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

Tool call example:

```bash
curl -X POST "https://<function-app-name>.azurewebsites.net/api/mcp" \\
	-H "Content-Type: application/json" \\
	-d '{"jsonrpc":"2.0","id":"2","method":"tools/call","params":{"name":"aks_get_cluster_details","arguments":{"subscription_id":"<sub>","resource_group":"<rg>","cluster_name":"<name>"}}}'
```

Optional environment variables:

- `AKS_MCP_HOST` (default: `0.0.0.0`)
- `AKS_MCP_PORT` (default: `8000`)

## Permissions required

The runtime identity needs permission to:

- Read AKS managed cluster and agent pool metadata.
- Execute AKS run command API for Kubernetes health checks and remediation commands.
- Have sufficient Kubernetes authorization for the requested remediation (for example, scaling a Deployment/StatefulSet or patching a PDB).

These roles are wired in later phases through infrastructure.

## Validation

At last repository validation: full test suite **277 passed**, focused async-upgrade suite **13 passed**. This MCP server was also validated deployed to Azure Container Apps (a specific revision responding to `tools/list` with HTTP 200 and exposing the required upgrade/status tools) — see the [root README's Validation / Test Results section](../../README.md#validation--test-results) for the point-in-time deployment snapshot and the real end-to-end live-cluster upgrade validation performed through this MCP server.
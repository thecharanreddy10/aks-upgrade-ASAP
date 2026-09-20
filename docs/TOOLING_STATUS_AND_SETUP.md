# AKS Upgrade Agent — Tooling Status & Setup Guide

This document describes the current state of the AKS Operations MCP tools and the Foundry
hosted agent that consumes them: what works, how far each capability is implemented, what is
still missing, and the exact steps required to stand this up in a different Azure subscription
(including which steps are already automated in code vs. which require a manual one-time action).

Last verified against: MCP revision `aks-mcp--0000058`, Foundry toolbox `aks-agent-tools-v19`,
agent version `47`. The live MCP registry exposes 29 tools.

---

## 1. What works today (validated live against `AKS_oldapp_cluster`)

### 1.1 Read-only assessment / discovery — fully working
- `aks_get_cluster_details`, `aks_get_node_pools`, `aks_get_available_upgrades`
- `aks_check_node_health`, `aks_check_pod_health`, `aks_check_pdb`, `aks_check_storage`,
  `aks_check_deprecated_apis` — the five **mandatory** upgrade-readiness checks.
- `aks_check_operator_health`,
  `aks_check_single_replica_services`, `aks_check_node_pool_surge`, `aks_check_priority_class`
  — advisory/optional checks, never auto-run, never treated as blockers.

### 1.2 Upgrade execution — fully working, staged, non-blocking
- `aks_plan_upgrade_preparation` — read-only plan; classifies each node pool as
  `SUPPORTED` / `UNSUPPORTED` / `INSUFFICIENT_EVIDENCE` / `CURRENT_WITH_CONTROL_PLANE` instead of
  treating "no Azure upgrade list yet" as evidence insufficiency.
- `aks_execute_confirmed_upgrade` (async coordinator) — submits at most one Azure long-running
  operation per call, requires `is_user_confirmed=True`, enforces `AKS_UPGRADE_ENABLE_WRITE=true`
  and `check_mode="full"`, refreshes node-pool evidence only after the control-plane operation
  completes, runs smoke checks after every stage, never bypasses the write gates.
- `aks_get_upgrade_execution_status` — for polling between stages.
- **Live-validated**: staged `complete_cluster` upgrade of `AKS_oldapp_cluster` from `1.35.6` to
  `1.35.7` completed successfully (control plane → node pool → final verification), with a
  correctly staged approval flow and no unauthorized writes.

### 1.3 Remediation — automatable (fully working, gated)
| Blocker | Tool | Notes |
|---|---|---|
| PDB blocks disruption | `aks_remediate_pdb` / `aks_rollback_pdb_remediation` | scale-up or relax strategies, explicit rollback tool |
| Unhealthy/stuck pods | `aks_remediate_pods` | rollout_restart / delete_pod |
| Node NotReady / pressure | `aks_remediate_node` | drain_node / restart_node |
| Deprecated API usage | `aks_remediate_deprecated_apis`, `aks_generate_deprecated_api_manifests` | evidence-based, never blind-patches apiVersion |
| Orphaned/terminating storage | `aks_remediate_storage` | cleanup_pvc / cleanup_pv only for eligible objects, never a healthy Bound PVC |

All write tools require `dry_run=False` **and** `check_mode="full"` **and**
`AKS_REMEDIATION_ENABLE_WRITE=true` (or `AKS_UPGRADE_ENABLE_WRITE=true` for upgrade execution).


---

## 2. Known limitation (not yet fixed)

**`kubectl auth can-i` verification runs without a valid Kubernetes API context in some code
paths**, causing it to try `localhost:8080` and fail with a connection-refused error instead of
returning a real allow/deny answer. This has been mitigated (the code now classifies this as an
`INCOMPLETE`/`applied_unverified` result instead of a false "permission denied"), but the
underlying cause — the AKS Run Command shell used for that specific verification call not having
`--as=` invoked against a properly initialized context — has not been root-caused/fixed. Treat any
`allowed: null` result as "could not be verified", not as "denied".

---

## 3. What is explicitly NOT automated (by design)

These are intentionally excluded from all automatic and dry-run-to-write paths. The agent will
only ever produce a read-only diagnosis and a list of manual steps for these:

- CRD schema conversion / CRD+operator upgrades / custom-resource migration
- RWO→RWX or RWX→RWO storage migration, StorageClass migration, volume data copy, workload
  storage cutover
- Application-specific data migration
- Backups and snapshots (etcd, PV snapshots, application-level backups)
- Helm/operator/CSI/CNI/ingress-controller **upgrades** (planning only — see §1.4)
- Node OS/container-runtime image changes (detected, not remediated)
- Webhook certificate **rotation** (planning only — see §1.4)

If you want any of these to become automatable, treat it as new work: add a dedicated,
narrowly-scoped write tool following the same pattern as the dedicated remediation tools
(exact-scope validation, post-write verification, explicit rollback where applicable).

---

## 4. Repository layout (where things live)

```
azure.yaml                                    # azd service definition (agent + ai-project)
src/agent-framework-agent-with-foundry-toolbox-responses/
    main.py                                   # Agent instructions (system prompt) + FoundryChatClient wiring
    toolbox.yaml                               # Points the Foundry toolbox at the MCP server_url
src/aks-operations-mcp/
    tools/registry.py                         # Single source of truth: ALL_TOOLS tuple exposed over MCP
    tools/upgrade.py                          # Inventory, readiness, staged-plan, smoke checks
    tools/async_upgrade.py                    # Non-blocking upgrade executor (aks_execute_confirmed_upgrade)
    tools/remediate_{pdb,pods,nodes,storage,deprecated_apis}.py  # existing dedicated write tools
    Dockerfile                                # MCP server container image
    tests/                                    # Full pytest suite (all green as of last run)
```

---

## 5. Setting this up in a different Azure subscription

Everything that can live in code already does (tool registration, safety gates, Dockerfile,
`azure.yaml`, `toolbox.yaml`). The steps below distinguish what `azd`/scripts do automatically
from what a human must do once per new subscription/cluster.

### 5.1 One-time manual prerequisites (cannot be scripted from inside this repo)
1. **Azure subscription access** with rights to create resource groups, Cognitive
   Services/Foundry, Container Apps, Container Registry, and role assignments.
2. **Target AKS cluster already exists** (this project does not create the AKS cluster itself).
3. **CLI tools installed locally**: `az` ≥ 2.57, `azd` ≥ 1.14, `docker` ≥ 24, `kubectl` ≥ 1.27,
   `python` ≥ 3.11.
4. **Azure login**: `az login` and `azd auth login` against the target tenant/subscription.

### 5.2 Automated by `azd` (code-driven, run once per environment)
```bash
azd init --cwd .
azd env new <environment-name>
azd provision      # creates resource group, Foundry project, Container App shell, ACR, identities
azd package        # builds and pushes both container images to ACR
azd deploy         # deploys the Foundry agent AND the MCP Container App
```
`azd provision` creates the managed identities and wires their client IDs into the Container
App's environment via `AZURE_CLIENT_ID` — no manual identity creation needed.

### 5.3 Manual step required after provisioning: grant the MCP identity access to the target cluster
This is **not** automated because the target AKS cluster is external to this repo's `azd`
environment and its resource group is not known in advance.

```bash
MCP_IDENTITY_ID=$(az containerapp show -n aks-mcp -g <mcp-resource-group> --query identity.principalId -o tsv)

az role assignment create \
  --role "Azure Kubernetes Service RBAC User" \
  --assignee $MCP_IDENTITY_ID \
  --scope /subscriptions/<target-sub>/resourceGroups/<target-rg>/providers/Microsoft.ContainerService/managedClusters/<cluster-name>
```
If the target cluster's node resource group also needs Run Command access, confirm the
identity also has **Azure Kubernetes Service Cluster User Role** or equivalent at the cluster
scope — this depends on the cluster's own RBAC/Azure AD integration configuration and must be
verified per-cluster.

### 5.4 Manual step: enable write gates (off by default, intentionally)
These are Container App environment variables, not something the code sets automatically,
because they must be an explicit operator decision:
```bash
az containerapp update -n aks-mcp -g <mcp-resource-group> \
  --set-env-vars AKS_UPGRADE_ENABLE_WRITE=true AKS_REMEDIATION_ENABLE_WRITE=true
```
Leave these `false`/unset in any environment that should stay assessment-only.

### 5.5 Manual step: point the agent at the right MCP toolbox
`src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml` contains the MCP
`server_url`. After every MCP code change you must:
```bash
azd ai toolbox create <new-toolbox-name> --from-file ./toolbox.yaml --project-endpoint <foundry-project-endpoint>
```
then update `TOOLBOX_ENDPOINT` in `azure.yaml`'s agent service block to the new toolbox's MCP
endpoint, then `azd deploy` again. This two-step (rebuild MCP image → new toolbox version →
redeploy agent) is required every time a tool signature or registry changes; it is not currently
scripted as a single command.

### 5.6 Validation after setup (all code-driven, no manual steps)
```bash
cd src/aks-operations-mcp
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q          # full suite should be green before trusting a new deployment

# Live tool-list check (adjust URL to the new Container App FQDN)
python -c "import json,urllib.request; ..."   # confirm tools/list returns expected tool count
```

### 5.7 Summary: code vs. manual
| Step | Automated in code? |
|---|---|
| Tool registration, safety gates, schemas | Yes — `tools/registry.py` |
| Dockerfile / image build | Yes — `az acr build` from the existing `Dockerfile` |
| Foundry project, Container App, ACR, identities creation | Yes — `azd provision` |
| Agent + MCP deployment | Yes — `azd deploy` |
| Granting MCP identity access to the **target AKS cluster** | **Manual**, per cluster |
| Enabling `AKS_UPGRADE_ENABLE_WRITE` / `AKS_REMEDIATION_ENABLE_WRITE` | **Manual**, deliberate operator decision |
| Creating/updating the Foundry toolbox version after MCP changes | **Manual** two-step (`azd ai toolbox create` + `azure.yaml` edit) |
| Running the test suite before trusting a deployment | **Manual** (not wired into CI in this repo) |

---

## 6. Suggested next steps (in priority order)

1. Fix the `kubectl auth can-i` execution-context issue at its source (§2) so RBAC verification
   is conclusive instead of `INCOMPLETE`.
2. Wire `azd ai toolbox create` + `azure.yaml` update + `azd deploy` into a single script/task so
   MCP changes don't require three manual command sequences.
3. Add CI (GitHub Actions/Azure DevOps pipeline) to run `pytest` automatically on every change to
   `src/aks-operations-mcp`.
4. Add dedicated write tools (following the RBAC apply/rollback pattern) for the next-lowest-risk
   category — likely a supported AKS add-on version bump — before attempting Helm/operator or
   webhook-rotation writes.
5. Add a distributed lock for `aks_execute_confirmed_upgrade`'s in-progress tracking if this MCP
   is ever run with more than one replica (current lock is process-local only).

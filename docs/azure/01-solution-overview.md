# 01 — Solution Overview

## Problem Statement

Upgrading an Azure Kubernetes Service (AKS) cluster safely is operationally complex:

- **Assessment burden**: Manually checking cluster health, node readiness, pod status, storage constraints, deprecated APIs, and PodDisruptionBudget (PDB) constraints requires deep Kubernetes expertise and consumes hours
- **Error-prone execution**: Long-running upgrade operations (10-30+ minutes) can fail mid-operation; manual retries lack audit trails and can compound issues
- **Remediation friction**: Identifying and fixing blockers (unhealthy nodes, pending pods, storage issues, deprecated APIs) is manual; no automated staged remediation path
- **Approval gap**: No clear human-approval workflow; upgrades can be initiated without explicit authorization

## Solution: AKS Upgrade Agent

The **AKS Upgrade Agent** is a **Foundry hosted AI agent** that automates safe, staged AKS cluster upgrades while preserving explicit human oversight:

```
ASSESSMENT
├─ Cluster discovery
├─ Node health
├─ Pod health
├─ PodDisruptionBudget constraints
├─ Storage health
├─ Deprecated API checks
└─ Upgrade profile lookups
    │
    ▼
PLAN
├─ Control-plane target version
├─ Node-pool upgrade support (SUPPORTED/INSUFFICIENT_EVIDENCE/UNSUPPORTED)
├─ Recommended scope (control_plane_only vs complete_cluster)
└─ Identified blockers and recommendations
    │
    ▼
EXPLICIT HUMAN APPROVAL
├─ User reviews plan
└─ User approves specific upgrade (unambiguous statement required)
    │
    ▼
EXECUTION
├─ Control-plane upgrade (async)
│  ├─ Submit upgrade
│  ├─ Poll status
│  └─ Verify target reached
├─ Node-pool upgrades (if complete_cluster scope)
│  └─ (Repeat for each eligible pool)
└─ Post-upgrade verification
    │
    ▼
REMEDIATION (if needed)
├─ Detect upgrade blockers
├─ Propose remediation
├─ Get explicit approval
└─ Execute fix (PDB, pods, storage, deprecated APIs)
    │
    ▼
RETRY UPGRADE
└─ Re-run full assessment
```

## Key Capabilities

### 1. Automated Assessment
- **Cluster Discovery**: Current Kubernetes version, provisioning state, FQDN, node resource group, identity profile
- **Node Health**: Ready status, memory/disk/PID pressure flags
- **Pod Health**: Phase, restart counts, scheduling status, container health
- **PodDisruptionBudget Health**: Disruption budget constraints that could block draining
- **Storage Health**: Persistent volume/claim provisioning, capacity, attachment status
- **Deprecated API Detection**: Workloads using deprecated Kubernetes APIs (gitRepo, storage classes, etc.)
- **Upgrade Profile Lookup**: Authoritative Azure upgrade paths for control-plane and node-pools

### 2. Staged Upgrade Planning
- Determines control-plane upgrade path and target version
- Assesses node-pool upgrade support (SUPPORTED/INSUFFICIENT_EVIDENCE/UNSUPPORTED)
- Recommends scope (control_plane_only prevents unintended node-pool writes)
- Surfaces mandatory blockers and optional upgrade-smoothness recommendations

### 3. Explicit Human Approval
- Agent generates upgrade plan and **stops**
- Requires user's explicit, unambiguous approval (e.g., "Yes, I approve the control-plane upgrade to 1.35.1")
- Ambiguous statements ("looks good", "okay") are rejected
- Separate approval required for each remediation action

### 4. Asynchronous Upgrade Execution
- Non-blocking submission of Azure long-running operations
- Status polling without holding MCP request open
- Staged execution: control-plane first, then node-pools
- Automatic deduplication (prevents duplicate submissions if already in-progress)
- Terminal failure detection (Failed/Canceled state reporting)

### 5. Intelligent Blocker Remediation
- **PDB remediation**: Scale workload replicas or relax disruption budget
- **Pod remediation**: Restart unhealthy workloads, clear pending pods
- **Node remediation**: Cordon/drain unhealthy nodes
- **Storage remediation**: Clean up PVCs, trigger finalizer resolution
- **Deprecated API remediation**: Auto-patch deprecated API versions (e.g., gitRepo → git-sync pattern)

## Components

### 1. Foundry Hosted Agent
- **Runtime**: Python 3.13 in container
- **Framework**: Agent Framework (agent-framework-foundry)
- **Model**: gpt-5-mini (Azure OpenAI deployment)
- **Protocol**: Responses (Foundry agent protocol)
- **Deployment**: Azure Foundry Agent Service
- **Configuration**: `azure.yaml` (azd deployment descriptor)
- **Entry Point**: `src/agent-framework-agent-with-foundry-toolbox-responses/main.py`

### 2. AKS Operations MCP Server
- **Runtime**: Python 3.11
- **Framework**: FastMCP (streamable-http transport)
- **Deployment**: Azure Container Apps
- **Alternative hosting**: Azure Functions (JSON-RPC endpoint at `/api/mcp`)
- **Configuration**: Environment variables for write gates, remediation gates
- **Tools exposed**: 29 read/write tools (see [02-component-inventory.md](02-component-inventory.md))
- **Entry Points**: 
  - `src/aks-operations-mcp/main.py` (FastMCP server)
  - `src/aks-operations-mcp/function_app.py` (Azure Functions)

### 3. Foundry Toolbox
- **Role**: MCP tool discovery and routing layer
- **Protocol**: MCP Streamable HTTP
- **Endpoint**: https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/.../toolboxes/aks-agent-tools-v2/versions/1/mcp
- **Configuration**: `src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml`

### 4. Azure AI Foundry Resources
- **AI Services Hub**: Cognitive Services account (cog-vtjc46vefyyj6)
- **AI Project**: agent-framework-agent-with-found
- **Model Deployment**: gpt-5-mini (Azure OpenAI)
- **Managed Identity**: User-assigned identity for agent runtime

### 5. Target AKS Cluster
- **Customer's infrastructure**: The AKS cluster to be upgraded
- **Identity requirement**: Managed identity with appropriate RBAC roles (see [08-security-and-identity.md](08-security-and-identity.md))
- **Access mechanism**: Azure SDK calls + Kubernetes API (via AKS Run Command)

## Safety Model

### Write Gatekeeping
All write operations (upgrades, remediations) are protected by **multiple authorization gates**:

1. **Explicit User Confirmation** (`is_user_confirmed=True`)
   - Agent instructions mandate clear, unambiguous approval
   - Example valid approval: "Yes, I approve the control-plane upgrade to 1.35.1"
   - Example invalid: "looks good", "okay", approval from earlier conversation

2. **Write Enable Flags** (Environment variables)
   - `AKS_UPGRADE_ENABLE_WRITE=true` (must be explicitly set)
   - `AKS_REMEDIATION_ENABLE_WRITE=true` (for remediation tools)
   - Default: both `false` (all writes blocked)

3. **Check Mode Enforcement** (`check_mode="full"`)
   - Only `check_mode="full"` allows writes
   - `check_mode="quick"` is read-only (prevents accidental writes)

4. **Scope Enforcement** (`confirmed_scope`)
   - `control_plane_only`: Control plane only, no node-pool writes
   - `complete_cluster`: Control plane + node-pools (if SUPPORTED evidence)
   - Prevents unintended node-pool modifications under control_plane_only scope

5. **RBAC Permissions** (Azure/Kubernetes identity)
   - Managed identity must have explicit roles assigned
   - Azure RBAC governs subscription/resource group access
   - Kubernetes RBAC governs cluster access via AKS Run Command

6. **Protected Namespaces**
   - Cluster-critical and system namespaces blocked from remediation:
     - `kube-system`, `kube-public`, `kube-node-lease`
     - `aks-command` (tool's own infrastructure)
     - `gatekeeper-system`, `calico-system`, `tigera-operator`

### Readiness Validation
Before any upgrade is executed, **mandatory** readiness checks must pass (or blockers must be surfaced):

- ✓ Cluster is in `Succeeded` provisioning state
- ✓ Control-plane target version is in authorized upgrade path
- ✓ All nodes are Ready (no NotReady, MemoryPressure, DiskPressure, PIDPressure)
- ✓ All pods are Running or Succeeded (no Pending, Failed, CrashLoopBackOff, ImagePullBackOff)
- ✓ PodDisruptionBudgets do not block all replicas (at least one eviction possible)
- ✓ Persistent volumes and claims are provisioned (no Pending or Failed)
- ✓ No deprecated Kubernetes APIs in use (or auto-remediation applied)

If any blocker is found, the upgrade is blocked. Agent can offer remediation for identified blockers.

## Workflow

### Typical User Interaction

```
USER:   "Can you assess if my AKS cluster is ready for upgrade to version 1.35.1?"

AGENT:  [Runs read-only assessment]
        - Cluster status: 1.35.0 → Ready for upgrade to 1.35.1
        - Control-plane: SUPPORTED
        - Node pools: pool1 SUPPORTED, pool2 INSUFFICIENT_EVIDENCE
        - Blockers: 3 pending pods in production namespace, 2 nodes have memory pressure
        - Recommendations: Fix pending pods, resolve memory pressure, or exclude pool2
        
        "The cluster is NOT YET ready. I found 3 blockers. Would you like me to:
         1. Run optional upgrade-smoothness checks?
         2. Help remediate the pending pods?
         3. Check storage or deprecated API issues?"

USER:   "Fix the pending pods and recheck"

AGENT:  [Gets explicit remediation approval]
        [Runs pod remediation]
        [Re-runs readiness assessment]
        - Pending pods: RESOLVED
        - Memory pressure: Still present on 2 nodes
        "Pending pods are fixed. Memory pressure remains on nodes. Would you like me to 
         drain and remediate those nodes, or proceed with the upgrade anyway?"

USER:   "Proceed with control-plane upgrade only"

AGENT:  "I'll upgrade the control plane to 1.35.1. This will NOT touch node pools. 
         Ready to proceed? (This is your approval to upgrade.)"

USER:   "Yes, proceed with the control-plane upgrade to 1.35.1"

AGENT:  [Explicit approval detected]
        [Calls aks_execute_confirmed_upgrade with is_user_confirmed=True, confirmed_scope="control_plane_only"]
        [Submits Azure upgrade operation (async)]
        "Upgrade submitted. Current status: In Progress. Monitoring..."
        
        [Polls status]
        "Control plane upgraded: 1.35.0 → 1.35.1. Provisioning state: Succeeded.
         Upgrade complete."
```

### Remediation Interaction

```
USER:   "Fix the deprecated gitRepo volume in namespace deprecated-test"

AGENT:  [Runs read-only check]
        "Found 1 pod using deprecated gitRepo in deployment gitrepo-test.
         I can replace it with git-sync init container pattern. Proceed?"

USER:   "Yes, fix it"

AGENT:  [Explicit remediation approval detected]
        [Calls aks_remediate_deprecated_apis with dry_run=False]
        [Verifies fix]
        "Remediation complete. Deployment patched, pod restarted successfully."
```

## Deployment Options

### Option 1: Default (Recommended)
- **Agent**: Foundry Hosted Agent Service
- **MCP Server**: Azure Container Apps
- **Deployment**: `azd deploy` (end-to-end)
- **Pros**: Fully managed, built-in observability, integrated with Foundry
- **Cons**: Foundry licensing required

### Option 2: Functions-Hosted MCP
- **Agent**: Foundry Hosted Agent Service
- **MCP Server**: Azure Functions (JSON-RPC at `/api/mcp`)
- **Deployment**: Manual Functions deployment, agent via azd
- **Pros**: Lower cost, use existing Functions infrastructure
- **Cons**: Manual MCP deployment, less observability

### Option 3: Self-Hosted Agent + MCP
- **Agent**: Custom orchestration (not Foundry)
- **MCP Server**: Container Apps or Functions
- **Deployment**: Custom
- **Pros**: Full control, use existing orchestration
- **Cons**: No built-in agent framework, manual observability

This guide assumes **Option 1** (default Foundry + Container Apps deployment).

## Resource Requirements

### Azure Subscription Resources

| Resource | Purpose | Tier/SKU | Monthly Cost (Estimate) |
|----------|---------|----------|------------------------|
| Cognitive Services (cog-*) | AI Services hub, OpenAI model | Standard S0 | $1-5 |
| Azure OpenAI Deployment (gpt-5-mini) | LLM model | gpt-5-mini | $0.002/1K input + $0.006/1K output tokens |
| Azure Container Apps (aks-mcp) | MCP server hosting | Dynamic consumption | $0.4/million requests + $0.05/vCPU/hr |
| Azure Container Registry (crccfxat3jn5lls) | Container image storage | Standard | $0.10/day + $0.10 per GB stored |
| Log Analytics Workspace | Logging/monitoring | Pay-as-you-go | $0.30/GB ingested |
| Managed Identity | Runtime identity | Free | $0 |
| Key Vault | Secrets storage (optional) | Standard | $0.60/month + key ops |

### Network Requirements

- **Outbound HTTP/HTTPS**: Agent → Foundry Project Endpoint, Foundry → MCP Endpoint
- **Firewall/NSG**: Depends on target cluster networking (see [07-network-architecture.md](07-network-architecture.md))
- **Connectivity**: MCP must reach target AKS cluster via Azure Management APIs + Kubernetes API

### Compliance & Governance

- **Data residency**: Azure region selection (eastus2 in validated deployment)
- **Encryption**: TLS in-transit (all HTTPS); encryption at-rest (Azure Storage managed keys)
- **Audit**: Azure Activity Log, Container App logs, Kubernetes audit logs
- **Access control**: RBAC, Managed Identity, no shared secrets

## Next Steps

1. **Understand the architecture**: Read [04-azure-architecture.md](04-azure-architecture.md)
2. **Verify prerequisites**: Read [09-prerequisites.md](09-prerequisites.md)
3. **Plan deployment**: Read [10-environment-configuration.md](10-environment-configuration.md) and [19-existing-environment-integration.md](19-existing-environment-integration.md)
4. **Deploy**: Follow [20-complete-deployment-runbook.md](20-complete-deployment-runbook.md) step-by-step
5. **Validate**: Run tests in [14-validation-and-smoke-tests.md](14-validation-and-smoke-tests.md)

---

**Status**: Production POC  
**Source Repository**: AISolutions-Virtusa/AKS-Upgrade-Agent  
**Last Updated**: 2026-09-10

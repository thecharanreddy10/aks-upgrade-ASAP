# 02 — Component Inventory

## Complete Solution Component List

This section inventories every component of the AKS Upgrade Agent solution, with purpose, technology, source location, runtime requirements, and dependencies.

| # | Component | Purpose | Technology | Source Location | Runtime | Input | Output | Key Dependencies | Azure Resource | Config Method |
|---|-----------|---------|-----------|-----------------|---------|-------|--------|------------------|----------------|----------------|
| 1 | Foundry Agent | Execute agent logic, consume MCP tools, interact with LLM | Python 3.13, Agent Framework (agent-framework-foundry), Responses Protocol | `src/agent-framework-agent-with-foundry-toolbox-responses/main.py` | Container (azd/Foundry) | User chat/invocation | Upgrade plan, remediation steps, status | Foundry Project, gpt-5-mini, Toolbox, DefaultAzureCredential | Foundry Hosted Agent Service | azure.yaml, env vars (FOUNDRY_PROJECT_ENDPOINT, AZURE_AI_MODEL_DEPLOYMENT_NAME, TOOLBOX_ENDPOINT) |
| 2 | Foundry Toolbox | Discover and route MCP tools to agent | Foundry metadata + MCP routing | `src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml` | Managed (Foundry) | Agent FoundryToolbox client | MCP tool schema + invocation | aks-operations-mcp endpoint | Foundry Toolbox Service | TOOLBOX_ENDPOINT (or FOUNDRY_PROJECT_ENDPOINT + TOOLBOX_NAME) |
| 3 | AKS Operations MCP Server | Expose AKS tools over MCP protocol | Python 3.11, FastMCP, streamable-http | `src/aks-operations-mcp/main.py` | Container App (Azure Container Apps) | MCP calls from agent | Tool results (JSON) | Azure SDK clients, Kubernetes API, Azure CLI | Container Apps (aks-mcp) | Environment variables (AKS_MCP_HOST, AKS_MCP_PORT, write/remediation gates) |
| 4 | Azure Functions MCP Entrypoint | Alternative MCP hosting (JSON-RPC) | Python 3.11, Azure Functions, FastMCP | `src/aks-operations-mcp/function_app.py` | Azure Functions | JSON-RPC POST requests | Tool results (JSON-RPC) | Azure SDK clients, Kubernetes API, Azure CLI | Azure Functions App | Same as MCP Server + Function key auth |
| 5 | Discovery Tools (aks_get_*) | Cluster/node pool discovery, upgrade profile lookup | Python async, Azure SDK (ContainerServiceClient) | `src/aks-operations-mcp/tools/discovery.py` | MCP Server runtime | subscription_id, resource_group, cluster_name | Cluster details, node pools, upgrade profiles | Azure subscription access, Azure API | Subscription | Implicit (via SDK authentication) |
| 6 | Validation Tools (aks_check_*) | Health checks (node, pod, PDB, storage, deprecated APIs) | Python async, Kubernetes API (AKS Run Command), Azure SDK | `src/aks-operations-mcp/tools/validation.py` | MCP Server runtime | subscription_id, resource_group, cluster_name, optional namespace | Health status, blockers, warnings | Target AKS cluster access, Kubernetes permissions | Target AKS Cluster | Environment variables (PROTECTED_NAMESPACES, remediation flags) |
| 7 | Upgrade Coordinator (aks_execute_confirmed_upgrade) | Non-blocking async AKS upgrade submission and status tracking | Python async, Azure SDK, threading.Lock (in-process) | `src/aks-operations-mcp/tools/upgrade.py` + `src/aks-operations-mcp/tools/async_upgrade.py` | MCP Server runtime | subscription_id, resource_group, cluster_name, target_kubernetes_version, is_user_confirmed, confirmed_scope | Upgrade execution state (blocked/in_progress/completed/partial/failed) | AKS APIs, readiness validation, Azure long-running operations | Target AKS Cluster, Subscription | Environment variables (AKS_UPGRADE_ENABLE_WRITE, check_mode, confirmed_scope) |
| 8 | CLI Operations (aks_kubectl_read/write, aks_az_read/write) | Generic kubectl and Azure CLI commands with allowlist | Python subprocess, allowlist-based filtering | `src/aks-operations-mcp/tools/cli_operations.py` | MCP Server runtime | command (kubectl/az) + arguments | Command output | Target cluster access, Azure CLI, managed identity auth | Target AKS Cluster | Allowlist maintained in tool (no config) |
| 9 | Remediation Tools (aks_remediate_*) | PDB, pod, node, storage, deprecated API remediation | Python async, Kubernetes API, Azure SDK | `src/aks-operations-mcp/tools/remediate_*.py` | MCP Server runtime | Resource details, dry_run flag, check_mode, confirmation flags | Remediation results, dry-run diff | Target cluster, Kubernetes permissions, Azure identity | Target AKS Cluster | Environment variables (AKS_REMEDIATION_ENABLE_WRITE) |
| 10 | Kubernetes Run Command Helper | Execute kubectl commands safely via AKS Run Command API | Python wrapper around Azure SDK RunCommandRequest | `src/aks-operations-mcp/tools/common.py` (run_kubectl_* functions) | MCP Server runtime | subscription_id, resource_group, cluster_name, command | Command stdout/stderr, exit code | AKS Run Command API, Target cluster | Target AKS Cluster | Implicit (via Azure API) |
| 11 | Test Suite | Comprehensive mock-based validation (no live Azure) | Python pytest, mock SDK responses | `src/aks-operations-mcp/tests/test_*.py` | CI/CD, local development | Test fixtures, mock clients | Test results (pass/fail) | pytest, monkeypatch, local fixtures | None | Implicit (test fixtures) |
| 12 | Dockerfile (Agent) | Container image for Foundry agent | Python 3.12-slim, pip, bytecode compilation | `src/agent-framework-agent-with-foundry-toolbox-responses/Dockerfile` | Build-time (CI/CD) | requirements.txt, source code | Container image | Python dependencies, pip | Container Registry (ACR) | Implicit (build artifact) |
| 13 | Dockerfile (MCP) | Container image for MCP server | Python 3.11-slim, pip, Azure CLI | `src/aks-operations-mcp/Dockerfile` | Build-time (CI/CD) | requirements.txt, source code, apt packages | Container image with Azure CLI | Python dependencies, pip, Azure CLI (for aks_az_* tools) | Container Registry (ACR) | Implicit (build artifact) |
| 14 | Container Registry (ACR) | Store agent and MCP server images | Azure Container Registry | crccfxat3jn5lls.azurecr.io | Runtime reference | Docker images | Image pull | Image tags, authentication | Azure Container Registry | Implicit (Azure RBAC) |
| 15 | AI Foundry Hub (Cognitive Services) | LLM model hosting, AI project management | Cognitive Services account (Standard SKU S0) | cog-vtjc46vefyyj6.services.ai.azure.com | Managed (Azure) | API requests | LLM responses | Azure OpenAI Deployments, Managed Identity | Cognitive Services Account | Region: eastus2 |
| 16 | Azure OpenAI Deployment | LLM model (gpt-5-mini) | Azure OpenAI gpt-5-mini | Hosted in Cognitive Services | Managed (Azure) | Prompt + tools | Completion + tool calls | Foundry Agent Framework | OpenAI Deployment (within Cognitive Services) | AZURE_AI_MODEL_DEPLOYMENT_NAME |
| 17 | Foundry Project | Agent definition, model deployment, AI project metadata | Foundry metadata service | agent-framework-agent-with-found (within cog-*) | Managed (Foundry) | Agent scaffold, model selection | Agent endpoint, deployment status | AI Project resource, Cognitive Services | AI Project (logical) | FOUNDRY_PROJECT_ENDPOINT |
| 18 | Container App (MCP Server) | Managed container hosting for MCP server | Azure Container Apps, consumption plan | aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io | Managed (Azure) | Container image (ACR pull) | HTTPS endpoint (/mcp) | ACR, managed identity, env vars | Container Apps (aks-mcp) | Container App name, image, env vars, scale settings |
| 19 | Managed Identity (Agent) | Runtime identity for agent container | Azure AD Managed Identity (user-assigned) | 9e5aa7d1-a77e-45d5-ab0f-9b316acfc0da | Managed (Azure) | None (implicit in Azure) | Access tokens (Azure RBAC) | RBAC role assignments, target subscription/cluster | User-Assigned Managed Identity | Client ID bound to agent container |
| 20 | Managed Identity (MCP Server) | Runtime identity for MCP server container | Azure AD Managed Identity (system-assigned or user-assigned) | Varies per deployment | Managed (Azure) | None (implicit in Azure) | Access tokens (Azure RBAC), Kubernetes API access | RBAC role assignments, target subscription/cluster | System/User-Assigned Managed Identity | Container App identity settings |
| 21 | Azure Subscription | Azure account and resource billing scope | Azure subscription | bb0e2c9e-d7fb-45e4-92cf-654f380e6388 | Billing/governance | Resource provisioning requests | Resource allocation, billing | Resource group, resource providers | Azure Subscription | Implicit (no config) |
| 22 | Resource Group (Foundry) | Container for AI Foundry resources | Azure Resource Group | rg-agent-framework-agent-with-foundry-toolbox-responses-dev-526c3b27 | Grouping/billing | Resource definitions | Organized resources | Subscription, resources | Resource Group | Implicit (azd management) |
| 23 | Target AKS Cluster | Customer's Kubernetes cluster to be upgraded | Azure Kubernetes Service cluster | Customer subscription/RG | Customer-managed | kubectl commands, Azure APIs | Cluster state, upgrade status | Virtual Network, node VMs, system add-ons | AKS Cluster | AZURE_SUBSCRIPTION_ID, AZURE_RESOURCE_GROUP, cluster_name env vars |
| 24 | Log Analytics Workspace | Centralized logging for agent and MCP | Application Insights / Log Analytics | Linked to Container App | Managed (Azure) | Application logs, traces | Queryable logs (KQL) | Container App diagnostics settings | Log Analytics Workspace | Diagnostic settings on Container App |
| 25 | Environment Variables | Configuration parameters | Key-value pairs | Stored in azd .env, Container App settings, Function App settings | Runtime | Environment keys | Parsed values | No dependencies (read at startup) | Various Azure resources | azure.yaml, azd config, Container App env vars |
| 26 | Secrets (if used) | API keys, passwords, connection strings | Azure Key Vault (optional) or environment variables | Key Vault or secure Azure service setting | Runtime | Vault access | Secret values | Key Vault RBAC, managed identity | Key Vault (optional) | Explicit Key Vault integration or env vars |

## Component Dependencies

### Agent Component Dependencies
```
Foundry Hosted Agent
    ├─ Foundry Agent Framework (Python package)
    ├─ FoundryToolbox (MCP routing)
    │  └─ Foundry Project Endpoint
    ├─ FoundryChatClient
    │  └─ Azure OpenAI Deployment (gpt-5-mini)
    ├─ DefaultAzureCredential
    │  └─ Agent Managed Identity
    └─ Instructions (hardcoded in main.py)
```

### MCP Server Component Dependencies
```
AKS Operations MCP Server
    ├─ FastMCP framework
    ├─ Azure SDK
    │  ├─ ContainerServiceClient
    │  │  └─ AKS Cluster (Management APIs)
    │  ├─ RunCommandRequest
    │  │  └─ AKS Run Command API
    │  └─ DefaultAzureCredential
    │      └─ MCP Server Managed Identity
    ├─ Kubernetes API (via AKS Run Command)
    │  └─ Target Cluster (kubectl)
    ├─ Azure CLI (optional, for aks_az_* tools)
    │  └─ Cluster credentials (via managed identity)
    ├─ Tool Registry (all MCP tools)
    └─ Environment Variables (write gates, remediation gates)
```

### Execution Flow Dependencies
```
End User
    │ [Chat/Invoke]
    ▼
Foundry Agent Service (containers running FoundryAgent code)
    │ [DefaultAzureCredential → Agent Managed Identity]
    │ [FoundryToolbox + MCP call]
    ▼
Foundry Toolbox Service (MCP routing)
    │ [MCP Streamable HTTP]
    ▼
Container App (AKS Operations MCP Server)
    │ [DefaultAzureCredential → MCP Server Managed Identity]
    │ [Azure SDK + Kubernetes API]
    ├─────→ Azure Management APIs (AKS)
    │       └─ Target AKS Cluster
    └─────→ Kubernetes API (AKS Run Command)
            └─ Target Cluster (kubectl)
    │
    ▼
Response (tool results, JSON)
    │
    ▼
Agent (processes response, generates next step)
```

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **User Interface** | Browser (Azure AI Foundry chat, Teams integration possible) | Invoke agent, view status |
| **Agent** | Python 3.13, Agent Framework, Responses Protocol | LLM-powered orchestration |
| **MCP** | Python 3.11, FastMCP, Streamable HTTP | Tool discovery and invocation |
| **Azure SDKs** | azure-mgmt-containerservice, azure-identity, azure-functions | Cloud API integration |
| **Kubernetes** | kubectl (via AKS Run Command), Kubernetes Python client | Cluster operations |
| **Runtime** | Azure Container Apps, Azure Functions, Foundry Hosted Agent | Infrastructure |
| **Storage** | Log Analytics, Application Insights | Observability |
| **Compute** | Managed containers, no VMs required | Serverless architecture |
| **Identity** | Azure AD Managed Identity, RBAC | Security, no shared secrets |

## Critical Path Components

Components on the **critical path** (if unavailable, solution does not function):

1. **Foundry Agent Service** — If down, agent cannot run
2. **Azure OpenAI Deployment** — If offline, agent cannot generate responses
3. **Foundry Toolbox Service** — If unreachable, agent cannot invoke tools
4. **Container App (MCP Server)** — If down, tools unavailable
5. **Target AKS Cluster** — If unreachable, assessment/upgrade fails
6. **Managed Identity (Agent + MCP)** — If permissions missing, Azure/Kubernetes APIs fail

## Optional Components

Components that enhance functionality but are not strictly required:

1. **Azure Key Vault** — Secrets management (can use environment variables instead)
2. **Log Analytics Workspace** — Observability (Container App works without logging)
3. **Azure CLI** — Optional for aks_az_* tools (kubectl path is primary)
4. **Container Registry** — Only if custom image builds (can use existing images)

## Data Storage and Lifecycle

| Data | Source | Storage | Retention | Access |
|------|--------|---------|-----------|--------|
| Agent invocation logs | Foundry Agent Service | Application Insights | 30 days (default) | KQL queries, Portal |
| MCP tool invocation logs | Container App | Log Analytics | 30 days (default) | KQL queries, Portal |
| Upgrade operation status | Azure AKS API | Azure Activity Log | 90 days | Activity Log Portal |
| Agent instructions | Hardcoded in main.py | Source repository | Until updated | Source control |
| MCP tool code | Python source files | Source repository + ACR | Version control | Source control + image tags |
| Cluster state snapshots | Agent → LLM context | In-memory (agent session) | Session lifetime | LLM context window |
| Environment configuration | azd .env, Container App settings | Azure Config Service | Until changed | Config Portal |

---

**Status**: Production POC  
**Last Updated**: 2026-09-10

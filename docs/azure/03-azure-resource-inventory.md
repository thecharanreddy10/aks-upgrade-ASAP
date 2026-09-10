# 03 — Azure Resource Inventory

## Every Azure Resource Required

This section identifies **every Azure resource** required to deploy and operate this solution, with justification, configuration, dependencies, and deployment method.

## Resource Dependency Graph

```
┌─────────────────────────────────────────────────────────┐
│ SUBSCRIPTION (bb0e2c9e-d7fb-45e4-92cf-654f380e6388)    │
└─────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
   [Foundation]      [AI Services]         [Hosting]
        │                   │                   │
        ├─ ResourceGroup    ├─ CognitiveServices   ├─ ContainerApp
        ├─ Tenant           │  ├─ Deployment      ├─ ContainerRegistry
        └─ Region           │  └─ Project         ├─ LogAnalyticsWorkspace
                            └─ ManagedIdentity    └─ ManagedIdentity

                      Additional for Enterprise:
                      ├─ KeyVault
                      ├─ VirtualNetwork
                      ├─ PrivateEndpoint
                      └─ NetworkSecurityGroup
```

## Core Azure Resources (Required)

### 1. Azure Subscription
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Subscription |
| **Purpose** | Billing and resource scope for all solutions |
| **Required** | ✓ Yes (mandatory) |
| **Code Location** | Implicit (not defined in IaC) |
| **Deployment Method** | Implicit (pre-existing Azure subscription) |
| **Why It's Required** | All resources must belong to a subscription for provisioning, billing, and RBAC |
| **Configuration** | `AZURE_SUBSCRIPTION_ID` environment variable |
| **Authentication** | Azure login (az login) |
| **RBAC Role Required** | Owner or Contributor |

### 2. Azure Tenant
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure AD Tenant |
| **Purpose** | Identity and access management |
| **Required** | ✓ Yes (implicit) |
| **Code Location** | Implicit (not defined in IaC) |
| **Why It's Required** | All identities (managed identities, user logins) belong to a tenant |
| **Configuration** | `AZURE_TENANT_ID` environment variable |
| **RBAC Role Required** | Subscription-level Contributor |

### 3. Resource Group
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Resource Group |
| **Name Pattern** | `rg-*` (e.g., `rg-agent-framework-agent-with-foundry-toolbox-responses-dev-526c3b27`) |
| **Purpose** | Container for related resources (billing, access, organization) |
| **Required** | ✓ Yes (mandatory) |
| **Typical Location** | eastus2 or customer's preferred region |
| **Code Location** | azd management (auto-created by `azd provision`) |
| **Deployment Method** | `azd provision` creates automatically, or `az group create` |
| **Why It's Required** | Azure requires all resources to belong to a resource group |
| **Permissions Required** | Subscription Contributor or Resource Group Contributor |
| **Cost** | $0 (no direct cost; billable resources grouped here) |

### 4. Cognitive Services Account (AI Foundry Hub)
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Cognitive Services |
| **Name** | `cog-vtjc46vefyyj6` (or similar) |
| **Purpose** | Hub for Azure AI services, model hosting, Azure OpenAI deployments |
| **Required** | ✓ Yes (required for Foundry agents + OpenAI) |
| **SKU** | Standard S0 (multi-service) |
| **Deployment Method** | `azd provision` (via Bicep/Terraform in .azure/) |
| **Code Location** | Infrastructure-as-Code (.azure/infra/main.bicep or main.tf) |
| **Authentication** | Managed Identity from agent container |
| **RBAC Role Required** | Cognitive Services Contributor (on service) |
| **Cost** | ~$1-5/month (S0 SKU) + per-model usage |
| **Configuration** | `AZURE_AI_ACCOUNT_NAME`, `AZURE_AI_PROJECT_NAME` |
| **Why It's Required** | Hosts Azure OpenAI deployments and Foundry project metadata |
| **Endpoint** | https://cog-vtjc46vefyyj6.services.ai.azure.com |
| **Key Params** | kind: "CognitiveServices", name: "OpenAI", deploymentName: "gpt-5-mini" |

### 5. Azure OpenAI Deployment
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure OpenAI Model Deployment |
| **Parent Resource** | Cognitive Services Account |
| **Model** | gpt-5-mini |
| **Purpose** | LLM for agent reasoning and tool invocation |
| **Required** | ✓ Yes (mandatory for agent logic) |
| **Deployment Method** | `azd provision` + manual gpt-5-mini model deployment |
| **Code Location** | Infrastructure-as-Code (.azure/infra/) or manual via Portal |
| **RBAC Role Required** | Cognitive Services OpenAI User (on deployment) |
| **Cost** | $0.002/1K input tokens + $0.006/1K output tokens (gpt-5-mini pricing) |
| **Configuration** | `AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5-mini"` |
| **Endpoint** | https://cog-vtjc46vefyyj6.openai.azure.com/ |
| **Key Params** | capacity: 10-100 (based on usage), version: latest |

### 6. Foundry AI Project
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Foundry Project (logical resource within Cognitive Services) |
| **Name** | `agent-framework-agent-with-found` |
| **Purpose** | Container for hosted agent definitions, model deployments, toolbox |
| **Required** | ✓ Yes (required for Foundry-hosted agents) |
| **Deployment Method** | `azd provision` (Foundry project creation via azd) |
| **Code Location** | azure.yaml + .azure/config.json |
| **RBAC Role Required** | Contributor on Cognitive Services |
| **Cost** | $0 (no separate cost; included in Cognitive Services) |
| **Endpoint** | https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found |
| **Configuration** | `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_AI_PROJECT_ID` |
| **Key Params** | region: eastus2, kind: "azure.ai.project" |

### 7. Azure Container Apps (MCP Server)
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Container Apps |
| **Name** | `aks-mcp` |
| **Purpose** | Managed container hosting for AKS Operations MCP server |
| **Required** | ✓ Yes (mandatory; exposes upgrade/remediation tools) |
| **Image** | `crccfxat3jn5lls.azurecr.io/aks-mcp:scope-enforcement-fix-20260909` |
| **Deployment Method** | `azd provision` or manual `az containerapp create` |
| **Tier** | Consumption (serverless, pay-per-request) |
| **Revision Name** | aks-mcp--0000024 (auto-managed) |
| **Endpoint** | https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp |
| **CPU/Memory** | 0.5 vCPU, 1 GiB RAM (from azure.yaml container.resources) |
| **Scaling** | Min 1, Max based on concurrency |
| **Port** | 80 (container), 443 (HTTPS ingress) |
| **Environment Variables** | AKS_MCP_HOST, AKS_MCP_PORT, AKS_UPGRADE_ENABLE_WRITE, AKS_REMEDIATION_ENABLE_WRITE, AZURE_CLIENT_ID |
| **RBAC Role Required** | Managed Identity User (for pulling image), AKS Cluster resource permissions |
| **Cost** | ~$0.4/million requests + $0.05/vCPU/hr |
| **Network** | Public endpoint (can be restricted with CORS/firewall) |
| **Key Params** | image: ACR reference, port: 80, environmentVariables: write gates, secrets: managed identity |

### 8. Azure Container Registry (ACR)
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Container Registry |
| **Name** | `crccfxat3jn5lls` |
| **Purpose** | Store agent and MCP server container images |
| **Required** | ✓ Yes (mandatory for Container App image pull) |
| **SKU** | Basic (or Standard for geo-replication) |
| **Deployment Method** | `azd provision` or manual `az acr create` |
| **Code Location** | Infrastructure-as-Code (.azure/infra/) |
| **RBAC Role Required** | AcrPull (for Container App), AcrPush (for CI/CD builds) |
| **Cost** | ~$0.10/day + storage costs (~$0.10/GB) |
| **Authentication** | Managed Identity (Container App pulls images) |
| **Key Params** | admin_enabled: false (use managed identity), sku: "Basic" |

### 9. Managed Identity (Agent)
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure AD User-Assigned Managed Identity |
| **Client ID** | 9e5aa7d1-a77e-45d5-ab0f-9b316acfc0da |
| **Purpose** | Runtime identity for agent container (no shared secrets) |
| **Required** | ✓ Yes (mandatory for secure Azure access) |
| **Deployment Method** | `azd provision` or manual `az identity create` |
| **Code Location** | Infrastructure-as-Code or Foundry auto-provisioning |
| **RBAC Roles Required** | Subscription or RG level: Contributor (for Foundry resources); Target cluster: AKS Cluster User Role (for kubectl via Run Command) |
| **Cost** | $0 (free) |
| **Principal ID** | 9e5aa7d1-a77e-45d5-ab0f-9b316acfc0da |
| **Assignment Scope** | Subscription, Resource Group, or specific resources |
| **Key Params** | identity_type: "UserAssigned", managed_identity_id: [...] |

### 10. Managed Identity (MCP Server / Container App)
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure AD System-Assigned or User-Assigned Managed Identity |
| **Purpose** | Runtime identity for Container App (no shared secrets) |
| **Required** | ✓ Yes (mandatory for Azure SDK calls from MCP server) |
| **Deployment Method** | Container App system-assigned (auto) or explicit user-assigned |
| **RBAC Roles Required** | Target subscription: Contributor; Target cluster: AKS Cluster User Role; ACR: AcrPull |
| **Cost** | $0 (free) |
| **Configuration** | Container App identity settings (system-assigned by default) |
| **Key Params** | identity: { type: "SystemAssigned" } or user-assigned identity |

### 11. Log Analytics Workspace
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Log Analytics Workspace |
| **Purpose** | Centralized logging for Container App, Application Insights |
| **Required** | ✗ No (optional; improves observability) |
| **Deployment Method** | `azd provision` or manual `az monitor log-analytics workspace create` |
| **Code Location** | Infrastructure-as-Code (.azure/infra/) |
| **Retention** | 30 days (default) to 730 days (2 years) |
| **SKU** | Pay-As-You-Go (standard) |
| **RBAC Role Required** | Log Analytics Contributor |
| **Cost** | ~$0.30/GB ingested |
| **Key Params** | sku: "PerGB2018", retention_in_days: 30 |
| **Query Language** | KQL (Kusto Query Language) |

### 12. Application Insights
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Application Insights |
| **Purpose** | Application performance monitoring, traces, exceptions |
| **Required** | ✗ No (optional; improves observability) |
| **Deployment Method** | Auto-created with Container App diagnostics, or manual creation |
| **Code Location** | Infrastructure-as-Code (.azure/infra/) |
| **Linked Resource** | Log Analytics Workspace |
| **RBAC Role Required** | Application Insights Component Contributor |
| **Cost** | Included in Log Analytics per-GB pricing |
| **Key Params** | linked_to_log_analytics: true, workspace_id: [...] |

## Optional Enterprise Resources (Recommended for Production)

### 13. Azure Key Vault
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Key Vault |
| **Purpose** | Secrets storage (API keys, connection strings, passwords) |
| **Required** | ✗ No (optional; can use env vars, but secrets best-practice) |
| **Deployment Method** | Manual `az keyvault create` or infrastructure-as-code |
| **Code Location** | Not in current repository (external reference) |
| **SKU** | Standard |
| **RBAC Role Required** | Key Vault Secrets Officer (for secret management), Key Vault Secrets User (for runtime) |
| **Cost** | ~$0.60/month + $0.03/10K secret operations |
| **Authentication** | Managed Identity access (preferred) |
| **Key Params** | sku: "standard", enabled_for_disk_encryption: false, enable_purge_protection: true |
| **Why Optional** | Solution works with environment variables; Key Vault adds secret rotation, audit trail |

### 14. Azure Virtual Network
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Virtual Network |
| **Purpose** | Network isolation, private endpoints, controlled egress |
| **Required** | ✗ No (optional; recommended for enterprise security) |
| **Deployment Method** | Manual or infrastructure-as-code |
| **Code Location** | Not in current repository (external reference) |
| **CIDR Block** | Customer-defined (e.g., 10.0.0.0/16) |
| **Subnets** | Container Apps subnet, Private Endpoint subnet (if private endpoints used) |
| **RBAC Role Required** | Network Contributor |
| **Cost** | $0 (no direct cost; included in subscription) |
| **Why Optional** | Solution works with public endpoints; VNet adds network isolation for enterprise security |

### 15. Private Endpoints
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Private Endpoint |
| **Purpose** | Private connectivity to Cognitive Services, Container Apps (no public IP) |
| **Required** | ✗ No (optional; recommended for enterprise) |
| **Deployment Method** | Manual `az network private-endpoint create` or infrastructure-as-code |
| **Parent Resources** | Cognitive Services, Container App |
| **RBAC Role Required** | Network Contributor, Service owner role |
| **Cost** | ~$0.01/hour per endpoint |
| **Subnet** | Requires subnet within VNet |
| **Why Optional** | Solution works with public endpoints; Private Endpoints add network isolation |

### 16. Private DNS Zone
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Private DNS Zone |
| **Purpose** | DNS resolution for private endpoints |
| **Required** | ✗ No (only if using Private Endpoints) |
| **Deployment Method** | Manual or infrastructure-as-code |
| **RBAC Role Required** | Private DNS Zone Contributor |
| **Cost** | $0.50/month per zone |
| **Why Optional** | Only required with Private Endpoints; simplifies DNS routing |

### 17. Network Security Group
| Attribute | Value |
|-----------|-------|
| **Resource Type** | Azure Network Security Group |
| **Purpose** | Inbound/outbound traffic rules for network isolation |
| **Required** | ✗ No (optional; recommended for enterprise) |
| **Deployment Method** | Manual or infrastructure-as-code |
| **Associated With** | Container Apps VNet subnet |
| **RBAC Role Required** | Network Contributor |
| **Cost** | $0 (no direct cost; included in subscription) |
| **Why Optional** | Solution works without NSG; NSG adds traffic filtering |

## Resource Sizing and Configuration

### Compute Resources

| Resource | Sizing Rationale | Recommended Value |
|----------|------------------|-------------------|
| Container App CPU | MCP server processes requests sequentially; upgrade operations are long-running but not CPU-intensive | 0.5 vCPU (sufficient for tool processing) |
| Container App Memory | Tool execution (Azure SDK calls, Kubernetes queries) + JSON parsing requires modest memory | 1 GiB RAM |
| Container App Scaling | Replicas scale based on concurrent requests; writes are sequential (in-progress locking) | Min 1, Max 10 (adjust based on expected concurrency) |
| OpenAI gpt-5-mini Capacity | Agent reasoning + tool calling is low-latency; budget for burst spikes | 10-100 capacity units (adjust based on invocation frequency) |

### Storage

| Resource | Sizing Rationale | Recommended Value |
|----------|------------------|-------------------|
| Log Analytics Retention | Operational logs, traces, exceptions; balance cost vs. historical analysis | 30 days (default); extend to 90 days for longer-term analysis |
| Container Registry Size | Stores agent + MCP server images (each ~500MB); retention for 5-10 image versions | Budget ~5 GB total (2-3 images × 2-3 versions) |

## Minimal Deployment (Development/POC)

For a minimal deployment that meets requirements without enterprise features:

| Resource | Included | Why |
|----------|----------|-----|
| ✓ Subscription | Yes | Required |
| ✓ Resource Group | Yes | Required |
| ✓ Cognitive Services (S0) | Yes | Required (Foundry + OpenAI) |
| ✓ Azure OpenAI Deployment | Yes | Required (LLM) |
| ✓ Foundry Project | Yes | Required (hosted agent) |
| ✓ Container App | Yes | Required (MCP server) |
| ✓ Container Registry | Yes | Required (image storage) |
| ✓ Managed Identity (×2) | Yes | Required (secure access) |
| ✗ Log Analytics Workspace | No | Optional (view logs in Portal) |
| ✗ Application Insights | No | Optional (included with Container App diagnostics) |
| ✗ Key Vault | No | Optional (use env vars, but add later for secrets rotation) |
| ✗ Virtual Network | No | Optional (use public endpoints) |
| ✗ Private Endpoints | No | Optional (add later for network isolation) |

## Production Deployment (Enterprise)

For a production deployment with enterprise best-practices:

| Resource | Included | Why |
|----------|----------|-----|
| All minimal resources | Yes | Foundation |
| ✓ Log Analytics Workspace | Yes | Centralized logging, audit trail |
| ✓ Application Insights | Yes | APM, performance monitoring |
| ✓ Key Vault | Yes | Secrets management, rotation |
| ✓ Virtual Network | Yes | Network isolation |
| ✓ Private Endpoints | Yes | No public IPs, controlled access |
| ✓ Private DNS Zone | Yes | DNS resolution for private endpoints |
| ✓ Network Security Groups | Yes | Traffic filtering |
| ✓ Azure Policy | Depends | Governance, compliance |

## Cost Estimation

### Monthly Costs (Minimal Deployment, Low Activity)

| Resource | Estimate | Notes |
|----------|----------|-------|
| Cognitive Services (S0) | $1-5 | Base S0 SKU |
| OpenAI gpt-5-mini | $5-20 | 100K-500K tokens/month at current pricing |
| Container App | $1-5 | Consumption: 0.4M requests @ $0.4/M, 10 hrs/month @ $0.05/vCPU |
| Container Registry | $3-5 | $0.10/day + storage (~$0.10/GB) |
| Log Analytics | $0 | Below free tier (< 1GB/month) |
| Managed Identity | $0 | Free |
| **Total** | **$10-35** | Minimal production baseline |

### Monthly Costs (Production Deployment, Moderate Activity)

| Resource | Estimate | Notes |
|----------|----------|-------|
| Cognitive Services (S0) | $5 | Base S0 SKU |
| OpenAI gpt-5-mini | $50-100 | 1M-2M tokens/month |
| Container App | $10-30 | Consumption: 2M requests, 50 hrs/month scaling |
| Container Registry | $5-10 | Standard SKU with 10GB storage |
| Log Analytics | $10-20 | 30-100 GB/month ingestion @ $0.30/GB |
| Key Vault | $1-2 | Base $0.60 + operations |
| Application Insights | (included) | Linked to Log Analytics |
| Network (VNet, Private Endpoints) | $1-3 | Base + 2 endpoints @ $0.01/hr |
| **Total** | **$82-160** | Production with observability |

---

**Next**: [04-azure-architecture.md](04-azure-architecture.md) for deployment diagrams  
**Status**: Production POC  
**Last Updated**: 2026-09-10

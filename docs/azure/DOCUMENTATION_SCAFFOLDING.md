# DOCUMENTATION SCAFFOLDING — Templates for Remaining 14 Documents

This document provides complete templates and guidance for creating the remaining 14 documentation files (06-19). Each template can be adapted to your specific deployment.

---

## Document 06 — Data Flow

**Purpose**: Complete data-flow documentation showing every request/response cycle

**Key Sections**:
1. **User Interaction Flow** — From chat input to agent response
2. **Tool Invocation Sequence** — MCP calls and responses
3. **Azure API Calls** — SDK calls to ARM, AKS Run Command, etc.
4. **Data Transformation** — How data changes through the pipeline
5. **Per-Connection Details** — Protocol, port, TLS, authentication for each connection
6. **Sequence Diagrams** — Mermaid sequence diagrams for common workflows
7. **Message Formats** — Example JSON/request payloads

**Template**:
```markdown
# 06 — Data Flow

## User Request Flow

### Path 1: Read-Only Assessment

User sends: "Can you assess my cluster?"

1. User sends chat message
2. Agent receives message
3. Agent decides: "Call aks_get_cluster_details"
4. Agent calls MCP tool
5. MCP calls Azure SDK
6. Azure API returns cluster state
7. Agent processes result
8. Agent decides: "Call aks_check_node_health"
... (repeat for each validation tool)
9. Agent compiles assessment report
10. Agent returns to user

### Path 2: Upgrade Execution

[Similar detailed flow for upgrade with approval gates]

## Per-Connection Details

| Connection | Protocol | Port | TLS | Authentication | Timeout |
|------------|----------|------|-----|---|---------|
| Browser → Agent | HTTPS | 443 | ✓ | OAuth (Foundry) | 5 min |
| Agent → LLM | HTTPS | 443 | ✓ | Managed Identity | 30s |
| Agent → Toolbox | HTTPS | 443 | ✓ | Token | 30s |
| Toolbox → MCP | HTTPS | 443 | ✓ | (Foundry managed) | 30s |
| MCP → Azure SDK | HTTPS | 443 | ✓ | Managed Identity | 30s |
| MCP → Kubernetes | HTTP/S | 443 | ✓ | Managed Identity | 30s |

## Message Formats

### Request: aks_get_cluster_details

```json
{
  "jsonrpc": "2.0",
  "id": "abc123",
  "method": "tools/call",
  "params": {
    "name": "aks_get_cluster_details",
    "arguments": {
      "subscription_id": "...",
      "resource_group": "...",
      "cluster_name": "..."
    }
  }
}
```

### Response: aks_get_cluster_details

```json
{
  "jsonrpc": "2.0",
  "id": "abc123",
  "result": {
    "subscription_id": "...",
    "resource_group": "...",
    "cluster_name": "...",
    "kubernetes_version": "1.35.0",
    "provisioning_state": "Succeeded",
    ...
  }
}
```

[Include diagrams: SequenceDiagram for each major workflow]
```

---

## Document 07 — Network Architecture

**Purpose**: Network topology, connectivity, private endpoints, firewall, DNS

**Key Sections**:
1. **Network Topology** — VNet diagram (if applicable)
2. **Public vs Private Endpoints** — Which are public, which are private
3. **Firewall Rules** — NSG, Azure Firewall (if used)
4. **Private Endpoints** — Private endpoint design (optional)
5. **DNS Resolution** — Public DNS, private DNS zones
6. **Bandwidth/Throughput** — Estimated data rates
7. **Latency Considerations** — End-to-end latency from user to cluster
8. **Multi-Region** — If supporting multiple regions

**Key Points for This Solution**:
- Default: All endpoints public (no VNet requirement)
- Optional: VNet + Private Endpoints for enterprise
- Outbound connectivity: HTTPS only (agents reach Azure APIs)
- No inbound requirements (agent invocation is user-initiated)

---

## Document 08 — Security and Identity

**Purpose**: Authentication, RBAC, secrets, encryption, compliance

**Key Sections**:
1. **Authentication** — Managed Identity, no shared secrets
2. **RBAC Matrix** — Who can do what on which resources
3. **Secret Management** — Where secrets are stored (Key Vault optional)
4. **Encryption** — In-transit (TLS), at-rest (Azure managed keys)
5. **Audit Trail** — Activity logging, approval logging
6. **Compliance** — SOC 2, HIPAA, PCI-DSS considerations
7. **Approval Workflow** — How explicit approval is enforced

**RBAC Matrix Template**:

| Identity | Resource | Role | Scope | Why |
|----------|----------|------|-------|-----|
| Agent Managed Identity | Subscription | Contributor | /subscriptions/... | Foundry resource access |
| MCP Managed Identity | AKS Cluster | AKS Cluster User | Cluster | kubectl/Run Command access |
| MCP Managed Identity | ACR | AcrPull | Registry | Image pull rights |
| User | Subscription | Contributor | /subscriptions/... | azd deployment |

---

## Document 10 — Environment Configuration

**Purpose**: Every environment variable, configuration parameter, secrets

**Key Sections**:
1. **All Environment Variables** — Table of every env var
2. **Where to Store** — Key Vault, Container App settings, env file
3. **Secrets vs Non-Secrets** — Which values are sensitive
4. **Example .env File** — Sample configuration
5. **Validation** — How to verify configuration is correct

**Environment Variables Table Template**:

| Variable | Purpose | Required | Example | Secret | Azure Source |
|----------|---------|----------|---------|--------|--------------|
| AZURE_SUBSCRIPTION_ID | Subscription ID | ✓ Yes | `bb0e2c9e-...` | ✗ No | Subscription |
| AZURE_RESOURCE_GROUP | Resource group name | ✓ Yes | `rg-aks-upgrade-agent` | ✗ No | azd output |
| AZURE_TENANT_ID | Tenant ID | ✓ Yes | `02a0a979-...` | ✗ No | Subscription |
| AZURE_CLIENT_ID | Managed identity client ID | ✓ Yes | `9e5aa7d1-...` | ✗ No | Managed Identity |
| FOUNDRY_PROJECT_ENDPOINT | Foundry project URL | ✓ Yes | `https://cog-*.services.ai.azure.com/...` | ✗ No | azd output |
| AZURE_AI_MODEL_DEPLOYMENT_NAME | LLM deployment name | ✓ Yes | `gpt-5-mini` | ✗ No | azure.yaml |
| TOOLBOX_ENDPOINT | MCP toolbox endpoint | ✓ Yes | `https://cog-*.services.ai.azure.com/.../mcp` | ✗ No | azd output |
| AKS_UPGRADE_ENABLE_WRITE | Enable upgrade writes | ✓ Yes | `false` (or `true` when approved) | ✗ No | Manual (safety gate) |
| AKS_REMEDIATION_ENABLE_WRITE | Enable remediation writes | ✓ Yes | `false` (or `true` when approved) | ✗ No | Manual (safety gate) |

---

## Document 11 — Azure Provisioning

**Purpose**: Step-by-step IaC provisioning (Bicep/Terraform templates)

**Key Sections**:
1. **Infrastructure Code** — Bicep/Terraform modules
2. **Resource Definitions** — Each resource's configuration
3. **Dependency Order** — What must be created first
4. **Parameters** — Customizable values (region, SKU, etc.)
5. **Outputs** — Resource IDs, endpoints for use by deployment
6. **Deployment Commands** — How to apply IaC

**This repository uses `azure.yaml` + azd**, so this document would reference:
- `.azure/infra/main.bicep` or `.azure/infra/main.tf`
- How azd manages infrastructure
- How to customize infrastructure for your environment

---

## Document 12 — Application Deployment

**Purpose**: Agent and MCP server deployment procedures

**Key Sections**:
1. **Agent Deployment** — Foundry Agent Service deployment
2. **MCP Deployment** — Container App deployment
3. **Alternative: Functions** — Azure Functions deployment option
4. **Version Management** — Agent versioning, rollback
5. **Health Checks** — How to verify deployment succeeded
6. **Observability** — Logging configuration

---

## Document 13 — CI/CD Deployment

**Purpose**: Continuous integration and deployment pipelines

**Key Sections**:
1. **CI Pipeline** — Build, test, security scan
2. **CD Pipeline** — Infrastructure provisioning, application deployment
3. **Branch Strategy** — When to deploy (main, staging, etc.)
4. **Approval Gates** — Manual approvals before production
5. **Rollback Strategy** — How to rollback in CI/CD
6. **Example Pipelines** — GitHub Actions or Azure DevOps YAML

**Note**: This repo uses Azure DevOps (mentioned in README), not GitHub Actions. Provide template for Azure Pipelines.

---

## Document 14 — Validation and Smoke Tests

**Purpose**: Post-deployment validation, health checks, smoke tests

**Key Sections**:
1. **Smoke Test Scripts** — Bash/PowerShell scripts to validate deployment
2. **Validation Checklist** — Manual verification steps
3. **Health Check Endpoints** — Which endpoints to query
4. **Expected Results** — What successful outputs look like
5. **Troubleshooting** — Common failures and fixes

**Smoke Test Examples**:

```bash
# 1. Authentication Test
az account show  # Verify logged in

# 2. Infrastructure Test
azd show  # Verify resources deployed

# 3. Agent Health Test
az containerapp logs show -n aks-mcp -g <rg>  # Check logs

# 4. MCP Connectivity Test
curl -X POST <mcp-endpoint>/mcp -d '{"jsonrpc":"2.0",...}'

# 5. Tool List Test
# Verify all 29 tools are available

# 6. Read-Only Assessment Test
azd ai agent invoke "Assess my cluster"  # Should succeed

# 7. Cluster Access Test
az aks command invoke -n <cluster> -g <rg> --command "kubectl get nodes"
```

---

## Document 15 — Troubleshooting

**Purpose**: Problem diagnosis and resolution

**Key Sections**:
1. **Troubleshooting Matrix** — Symptom → Cause → Solution
2. **Log Analysis** — How to read logs, query Log Analytics
3. **Common Issues** — Authentication, RBAC, connectivity, deployment
4. **Debug Commands** — Diagnostic commands to run
5. **Contact/Escalation** — How to get help

**Troubleshooting Matrix Template**:

| Symptom | Likely Cause | How to Check | Resolution |
|---------|------------|-------------|-----------|
| `aks-mcp` Container App not starting | Image pull failed | `az containerapp logs show -n aks-mcp -g <rg>` | Verify ACR access, managed identity has AcrPull role |
| Agent cannot reach MCP server | Toolbox endpoint wrong | `echo $TOOLBOX_ENDPOINT` | Verify in .env file, test with curl |
| MCP cannot reach target cluster | Wrong subscription ID | `az aks show -n <cluster> -g <rg>` | Verify cluster exists in target subscription |
| Upgrade succeeds but cluster not upgraded | Write gate disabled | `az containerapp show ... \| grep AKS_UPGRADE_ENABLE_WRITE` | Enable write gate, re-run upgrade |
| Tool times out | Network latency, overloaded cluster | Check MCP logs | Increase timeout, check cluster health |

---

## Document 16 — Rollback

**Purpose**: Rollback procedures for failed deployments or upgrades

**Key Sections**:
1. **Application Rollback** — Downgrade to previous agent version
2. **Infrastructure Rollback** — Tear down resources
3. **AKS Cluster Rollback** — Downgrade cluster version
4. **Data Recovery** — Restore from backups if needed
5. **Approval Process** — Who can initiate rollback

**Rollback Procedures**:

```bash
# Rollback Agent to Previous Version
azd down  # Destroy current deployment
git checkout <previous-commit>  # Go back to previous version
azd provision && azd deploy  # Redeploy

# Rollback AKS Cluster (if upgrade failed)
# Note: AKS does not support cluster downgrade
# Options:
# 1. Create new cluster with older version
# 2. Provision replacement cluster
# 3. Accept failure and plan recovery

# Rollback Infrastructure
az group delete -n <rg> --yes  # Delete resource group + all resources
azd provision  # Recreate fresh infrastructure
```

---

## Document 17 — Operations and Monitoring

**Purpose**: Day-2 operations, monitoring, alerting, maintenance

**Key Sections**:
1. **Monitoring Dashboards** — Key metrics to watch
2. **Alerting Rules** — When to alert operations
3. **Log Queries** — KQL queries for common troubleshooting
4. **Maintenance Windows** — When to perform updates
5. **Capacity Planning** — When to scale up
6. **Runbooks** — Common operational tasks

**Key Metrics to Monitor**:
- Agent invocation rate (requests/minute)
- Agent response time (median, p95, p99)
- Tool execution time (by tool)
- Error rate (% of failures)
- MCP server CPU/memory usage
- Log Analytics ingestion rate (GB/day)
- Cost per invocation

---

## Document 18 — Cost and Scaling

**Purpose**: Cost drivers, cost optimization, scaling strategy

**Key Sections**:
1. **Cost Breakdown** — Cost per resource per month
2. **Cost Drivers** — What impacts cost most
3. **Cost Optimization** — How to reduce spending
4. **Scaling Limits** — Min/max configurations
5. **Right-Sizing** — Adjust SKUs based on usage
6. **Reserved Instances** — RI options (if applicable)

**Cost Optimization Examples**:
- Container App scaling: Reduce max replicas if not needed
- Log retention: Reduce from 90 days to 30 days
- OpenAI model: Switch from gpt-5 to gpt-4 if acceptable
- ACR tier: Use Basic instead of Standard if single region

---

## Document 19 — Existing Environment Integration

**Purpose**: Integrating into existing Azure environments, reusing resources

**Key Sections**:
1. **Resource Reuse Matrix** — Which existing resources can be reused
2. **Configuration Changes** — What needs to change when reusing
3. **Existing Environment Checklist** — Pre-deployment requirements
4. **Migration Procedure** — How to move from existing setup

**Existing Environment Checklist**:

| Existing Resource | Can Reuse | Configuration Changes | Validation |
|-------------------|-----------|----------------------|-----------|
| Subscription | Yes | Specify in `AZURE_SUBSCRIPTION_ID` | `az account set --subscription <id>` |
| Resource Group | Yes (if permissions allow) | Use existing RG name | `az group show -n <name>` |
| Cognitive Services | Possibly | If gpt-5-mini already deployed | `az cognitiveservices account show ...` |
| Container Registry | Yes | Reference existing registry | `az acr show -n <name>` |
| Virtual Network | Yes | Configure private endpoints | `az network vnet show ...` |
| Log Analytics | Yes | Link Container App to existing workspace | `az monitor log-analytics workspace show ...` |
| Key Vault | Yes | Update managed identity access policies | `az keyvault show ...` |
| AKS Cluster | Yes (target) | Specify in configuration | `az aks show -n <name> -g <rg>` |

---

## Document 25 — Assumptions and Gaps

**Purpose**: Document everything that could NOT be conclusively determined from the repository

**Key Sections**:
1. **Unknown Decisions** — Design decisions without clear evidence
2. **Unverified Assumptions** — Assumptions about production setup
3. **Incomplete Information** — Information not found in repo
4. **Recommended Confirmations** — How to resolve unknowns
5. **Impact Assessment** — How unknowns affect deployment

**Example Assumptions**:

| Unknown | Evidence Searched | Why Inconclusive | Recommended Confirmation | Impact |
|---------|-------------------|------------------|-------------------------|--------|
| Exact CI/CD platform | README says "Azure DevOps" but no .devops folder | No pipeline YAML in repo | Ask deployment team which CI platform | Must create matching pipeline templates |
| Multi-region strategy | Single region (eastus2) in validated deployment | No geo-replication config | Clarify regional requirements | Affects Traffic Manager, ACR geo-replication setup |
| Disaster recovery RPO/RTO | No DR documentation in repo | No backup/restore scripts | Define RPO/RTO targets | Affects backup strategy, failover design |
| Budget limits | No cost cap or alerts configured | No cost management policies | Define monthly budget limit | Affects Container App scaling limits |

---

## How to Complete Each Document

1. **Copy the template** from the relevant section above
2. **Customize for your deployment** — Replace placeholders, add specifics
3. **Reference the repository** — Link to source files where applicable
4. **Include examples** — Real outputs from your deployment
5. **Validate with teams** — Security, operations, architecture review
6. **Version control** — Commit documentation updates with code

---

## Document Priority

**Create First** (critical for deployment):
1. ✓ 06 — Data Flow
2. ✓ 09 — Prerequisites  
3. ✓ 20 — Deployment Runbook
4. 10 — Environment Configuration
5. 14 — Validation and Smoke Tests

**Create Second** (important for operations):
6. 07 — Network Architecture
7. 08 — Security and Identity
8. 15 — Troubleshooting
9. 17 — Operations and Monitoring
10. 16 — Rollback

**Create Third** (nice-to-have):
11. 11 — Azure Provisioning
12. 12 — Application Deployment
13. 13 — CI/CD Deployment
14. 18 — Cost and Scaling
15. 19 — Existing Environment Integration
16. 25 — Assumptions and Gaps

---

**Status**: Scaffolding Complete  
**Next Step**: Populate each document using templates above  
**Estimated Time**: 4-8 hours for complete documentation  
**Last Updated**: 2026-09-10

# 20 — Complete Deployment Runbook

## Step-by-Step Deployment Guide

This runbook provides **executable commands** to deploy the AKS Upgrade Agent solution into an existing Azure environment. Follow each step sequentially.

### Prerequisites Verification

**Before Starting**: Complete all steps in [09-prerequisites.md](09-prerequisites.md)

```bash
# Verify tools
az --version                    # >= 2.57.0
azd version                     # >= 1.14.0
docker --version                # >= 24.0
kubectl version --client        # >= 1.27.0
python --version                # >= 3.11

# Verify authentication
az account show

# Set working directory
cd /path/to/aks-ai-upgrade-agent-2
```

## PHASE 1 — Foundation (0-5 minutes)

### Step 1.1 — Initialize Azure Developer CLI

**Purpose**: Set up azd environment and local configuration

**Command**:
```bash
azd init --cwd .
```

**Expected Output**:
```
✓ Successfully initialized AKS Upgrade Agent
Environment: aks-ai-upgrade-agent-2
```

**Troubleshooting**:
- If init fails, delete `.azure/` directory and retry
- Verify `.azure/config.json` exists after init

### Step 1.2 — Verify Environment Configuration

**Purpose**: Confirm environment name and subscription

**Command**:
```bash
cat .azure/config.json

azd env show
```

**Expected Output**:
```json
{
  "version": 1,
  "defaultEnvironment": "aks-ai-upgrade-agent-2"
}
```

**Configuration**:
```
Environment: aks-ai-upgrade-agent-2
Subscription: bb0e2c9e-d7fb-45e4-92cf-654f380e6388
Tenant: 02a0a979-8c72-4fa4-bb66-e07b1d185b5b
Location: eastus2
```

## PHASE 2 — Infrastructure Provisioning (5-15 minutes)

### Step 2.1 — Provision Azure Resources

**Purpose**: Create Cognitive Services, Container Apps, managed identities, logging, and networking

**Command**:
```bash
azd provision
```

**What It Does**:
1. Creates Resource Group (auto-named)
2. Deploys Cognitive Services account (S0 SKU)
3. Deploys Azure OpenAI gpt-5-mini model
4. Creates Foundry Project
5. Creates Container App (MCP server placeholder)
6. Creates Container Registry (ACR)
7. Creates Log Analytics Workspace
8. Creates managed identities (agent + MCP)
9. Assigns RBAC roles
10. Generates `.env` and `.env.lock` files

**Expected Output**:
```
✓ Provisioning Azure resources...
✓ Resource Group: rg-agent-framework-agent-with-foundry-toolbox-responses-dev-*
✓ Cognitive Services: cog-*
✓ Container Apps: aks-mcp
✓ Container Registry: crccfxat3jn5lls
✓ Log Analytics: log-*
✓ Managed Identities: agent-id, mcp-id
✓ Provisioning complete in ~10 minutes
```

**Configuration Files Updated**:
- `.azure/aks-ai-upgrade-agent-2/.env` — Contains all deployed resource IDs and endpoints
- `.azure/aks-ai-upgrade-agent-2/.env.lock` — Locked configuration (do not edit)

**Validation**:
```bash
# Verify resource group exists
az group show -n $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2)

# Verify Cognitive Services
az cognitiveservices account show -n $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_AI_ACCOUNT_NAME | cut -d= -f2) -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2)

# Verify Container Registry
az acr show -n $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_CONTAINER_REGISTRY_NAME | cut -d= -f2)
```

**Troubleshooting**:
- If provisioning fails, run `azd provision` again (idempotent)
- If quota exceeded, request quota increase and retry
- If resource already exists, delete via portal and retry

### Step 2.2 — Configure Target AKS Cluster Access

**Purpose**: Set up managed identity with permissions to target AKS cluster

**Command**:
```bash
# Export variables from .env
source <(grep -v '^#' .azure/aks-ai-upgrade-agent-2/.env | xargs)

# Get MCP server managed identity
MCP_IDENTITY_ID=$(az containerapp show -n aks-mcp -g $AZURE_RESOURCE_GROUP --query identity.principalId -o tsv)

# Get target AKS cluster (update with your cluster name/RG)
TARGET_SUBSCRIPTION="<customer-subscription-id>"
TARGET_RESOURCE_GROUP="<customer-rg>"
TARGET_CLUSTER="<cluster-name>"

# Assign AKS Cluster User Role to MCP identity
az role assignment create \
  --role "Azure Kubernetes Service RBAC User" \
  --assignee $MCP_IDENTITY_ID \
  --scope /subscriptions/$TARGET_SUBSCRIPTION/resourcegroups/$TARGET_RESOURCE_GROUP/providers/Microsoft.ContainerService/managedClusters/$TARGET_CLUSTER
```

**Expected Output**:
```
{
  "id": "/subscriptions/.../roleAssignments/...",
  "principalId": "...",
  "roleDefinitionId": "...",
  "roleDefinitionName": "Azure Kubernetes Service RBAC User",
  "scope": "/subscriptions/.../..."
}
```

**Validation**:
```bash
# Verify role assignment
az role assignment list \
  --assignee $MCP_IDENTITY_ID \
  --include-inherited --output table
```

**If Target Cluster is in Different Subscription**:
```bash
# Use cross-subscription RBAC
az role assignment create \
  --role "Azure Kubernetes Service RBAC User" \
  --assignee $MCP_IDENTITY_ID \
  --scope /subscriptions/$TARGET_SUBSCRIPTION/resourcegroups/$TARGET_RESOURCE_GROUP/providers/Microsoft.ContainerService/managedClusters/$TARGET_CLUSTER \
  --subscription $TARGET_SUBSCRIPTION
```

## PHASE 3 — Build and Containerization (5-10 minutes)

### Step 3.1 — Build and Push Container Images

**Purpose**: Build agent and MCP server images, push to ACR

**Command**:
```bash
azd package
```

**What It Does**:
1. Builds agent Docker image (`src/agent-framework-agent-with-foundry-toolbox-responses/Dockerfile`)
2. Builds MCP server Docker image (`src/aks-operations-mcp/Dockerfile`)
3. Tags images with commit hash + timestamp
4. Pushes to Container Registry

**Expected Output**:
```
✓ Building agent image...
✓ Agent image pushed: crccfxat3jn5lls.azurecr.io/agent-framework-agent-with-foundry-toolbox-responses:*
✓ Building MCP server image...
✓ MCP image pushed: crccfxat3jn5lls.azurecr.io/aks-mcp:*
✓ Packaging complete
```

**Validation**:
```bash
# List images in ACR
az acr repository list -n $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_CONTAINER_REGISTRY_NAME | cut -d= -f2)

# Verify image tags
az acr repository show-tags -n <registry> --repository aks-mcp
```

**Troubleshooting**:
- If ACR login fails, verify managed identity has AcrPush role
- If Docker build fails, check Dockerfile for syntax errors
- If push fails, verify ACR exists and is accessible

## PHASE 4 — Application Deployment (10-20 minutes)

### Step 4.1 — Deploy Agent and MCP Server

**Purpose**: Deploy Foundry agent and MCP server to their runtime environments

**Command**:
```bash
azd deploy
```

**What It Does**:
1. Deploys Foundry Agent Service (using `azure.yaml` configuration)
2. Deploys Container App (MCP server)
3. Configures environment variables (write gates, remediation gates)
4. Assigns managed identities
5. Configures diagnostics (logging)
6. Waits for health checks

**Expected Output**:
```
✓ Deploying agent to Foundry...
✓ Agent endpoint: https://cog-*.services.ai.azure.com/api/projects/.../agents/.../versions/1
✓ Deploying MCP server to Container App...
✓ MCP endpoint: https://aks-mcp.*.azurecontainerapps.io/mcp
✓ Deployment complete in ~15 minutes
```

**Validation**:
```bash
# Verify agent deployment
azd show                                # Shows deployment status

# Verify Container App is running
az containerapp show -n aks-mcp -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --query "properties.runningStatus"

# Test MCP endpoint
curl -X POST https://aks-mcp.*.azurecontainerapps.io/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

**Troubleshooting**:
- If agent deployment fails, check Foundry project health
- If Container App doesn't start, check logs: `az containerapp logs show -n aks-mcp -g <rg>`
- If MCP endpoint unreachable, check NSG/firewall rules

### Step 4.2 — Verify Write Gate Configuration

**Purpose**: Ensure write protection is in place (write gates disabled by default)

**Command**:
```bash
# Export variables
source <(grep -v '^#' .azure/aks-ai-upgrade-agent-2/.env | xargs)

# Check current write gate status (should be false)
az containerapp show -n aks-mcp -g $AZURE_RESOURCE_GROUP --query "properties.template.containers[0].env[?name=='AKS_UPGRADE_ENABLE_WRITE'].value"

# Verify remediation gate is disabled
az containerapp show -n aks-mcp -g $AZURE_RESOURCE_GROUP --query "properties.template.containers[0].env[?name=='AKS_REMEDIATION_ENABLE_WRITE'].value"
```

**Expected Output**:
```
"false"  # Write gates should be disabled initially
```

**Note**: Write gates remain disabled until explicitly enabled (see "Enable Write Gates" section below).

## PHASE 5 — Validation (5-10 minutes)

### Step 5.1 — Test Agent Locally

**Purpose**: Verify agent can start and respond to commands

**Command**:
```bash
# Option 1: Run agent locally for testing
azd ai agent run

# In another terminal, test locally
azd ai agent invoke --local "Hello, what is your name?"
```

**Expected Output**:
```
Local agent running on http://localhost:8088

Invocation complete
Response: "I'm the AKS Upgrade Agent..."
```

**Option 2**: If Foundry deployment is ready, test deployed agent:

```bash
# Invoke deployed agent
azd ai agent invoke "Hello, what is your name?"
```

### Step 5.2 — Run Smoke Tests

**Purpose**: Validate end-to-end connectivity and functionality

**Command**:
```bash
# Navigate to smoke tests directory
cd docs/azure/smoke-tests

# 1. Authentication test
./01-auth-test.sh

# 2. Infrastructure connectivity test
./02-infrastructure-test.sh

# 3. Agent health test
./03-app-health-test.sh

# 4. Tool availability test
./04-agent-test.sh
```

**Expected Output**:
```
✓ Authentication test passed
✓ Infrastructure test passed
✓ Agent health test passed
✓ Tool availability test passed
```

### Step 5.3 — Validate MCP Tools

**Purpose**: Verify all 29 MCP tools are available

**Command**:
```bash
# Get MCP endpoint from .env
source <(grep -v '^#' .azure/aks-ai-upgrade-agent-2/.env | xargs)
MCP_ENDPOINT=$(cat .azure/aks-ai-upgrade-agent-2/.env | grep TOOLBOX_ENDPOINT | cut -d= -f2 | tr -d '"')

# List tools
curl -s -X POST "$MCP_ENDPOINT" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}' | jq '.result.tools | length'
```

**Expected Output**:
```
29  # All 29 tools should be available
```

## PHASE 6 — Integration with Target Cluster (5 minutes)

### Step 6.1 — Store Target Cluster Credentials

**Purpose**: Configure agent to access target AKS cluster

**Command**:
```bash
# Option 1: Store in Container App environment variables
TARGET_SUBSCRIPTION="<subscription-id>"
TARGET_RESOURCE_GROUP="<resource-group>"
TARGET_CLUSTER="<cluster-name>"

az containerapp update -n aks-mcp \
  -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) \
  --set-env-vars \
    AZURE_SUBSCRIPTION_ID="$TARGET_SUBSCRIPTION" \
    AZURE_RESOURCE_GROUP="$TARGET_RESOURCE_GROUP" \
    AKS_CLUSTER_NAME="$TARGET_CLUSTER"
```

**Option 2**: Store in Key Vault (enterprise best-practice):

```bash
# Create Key Vault
KV_NAME="kv-aks-upgrade-agent-$(date +%s)"
az keyvault create -n $KV_NAME -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2)

# Store secrets
az keyvault secret set -n "target-subscription" -v "$TARGET_SUBSCRIPTION" --vault-name $KV_NAME
az keyvault secret set -n "target-resource-group" -v "$TARGET_RESOURCE_GROUP" --vault-name $KV_NAME
az keyvault secret set -n "target-cluster-name" -v "$TARGET_CLUSTER" --vault-name $KV_NAME

# Grant MCP managed identity access
MCP_IDENTITY_ID=$(az containerapp show -n aks-mcp -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --query identity.principalId -o tsv)
az keyvault set-policy -n $KV_NAME --secret-permissions get list --object-id $MCP_IDENTITY_ID

# Configure Container App to use Key Vault references
az containerapp update -n aks-mcp \
  -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) \
  --set-env-vars \
    AZURE_SUBSCRIPTION_ID="@Microsoft.KeyVault(SecretUri=https://$KV_NAME.vault.azure.net/secrets/target-subscription/)"
```

### Step 6.2 — Test Cluster Connectivity

**Purpose**: Verify MCP server can reach target cluster

**Command**:
```bash
# Get target cluster info
az aks show -n $TARGET_CLUSTER -g $TARGET_RESOURCE_GROUP

# Test AKS Run Command capability
az aks command invoke -n $TARGET_CLUSTER -g $TARGET_RESOURCE_GROUP --command "kubectl get nodes"
```

**Expected Output**:
```
NAME                              STATUS   ROLES   AGE   VERSION
aks-nodepool1-12345678-abcde      Ready    agent   30d   v1.35.0
aks-nodepool1-12345678-fghij      Ready    agent   30d   v1.35.0
```

## PHASE 7 — Testing (5-10 minutes)

### Step 7.1 — Run Read-Only Assessment

**Purpose**: Test agent can assess cluster without write operations

**Command**:
```bash
# Use agent to assess target cluster (no writes)
azd ai agent invoke "Can you assess if my AKS cluster is ready for upgrade to version 1.35.1?"
```

**Expected Output**:
```
Cluster Assessment:
- Current Version: 1.35.0
- Target Version: 1.35.1
- Control Plane Status: SUPPORTED
- Node Pools: pool1 SUPPORTED, pool2 INSUFFICIENT_EVIDENCE
- Blockers: [list of any]
- Recommendations: [list of recommendations]
```

**Validation**:
```bash
# Verify no Azure resources were modified
az aks show -n $TARGET_CLUSTER -g $TARGET_RESOURCE_GROUP --query "kubernetes_version"
# Should still show 1.35.0 (no upgrade yet)
```

### Step 7.2 — Run Upgrade Dry-Run (if applicable)

**Purpose**: Test upgrade workflow without actual execution

**Command**:
```bash
# Request upgrade with explicit approval
azd ai agent invoke "I approve the control-plane upgrade to 1.35.1 to verify the workflow."
```

**Expected Output**:
```
Upgrade Submitted:
- Status: in_progress
- Target: 1.35.1
- Scope: control_plane_only
- Current Provisioning State: Succeeded

Note: Write gates may be disabled. Upgrade not executed.
```

**Validation**:
```bash
# Verify cluster version unchanged
az aks show -n $TARGET_CLUSTER -g $TARGET_RESOURCE_GROUP --query "kubernetes_version"
```

## PHASE 8 — Production Configuration (5 minutes)

### Step 8.1 — Enable Write Gates (When Ready)

**Purpose**: Allow actual upgrade and remediation operations

**Command**:
```bash
# IMPORTANT: Only enable after thorough testing and approval

source <(grep -v '^#' .azure/aks-ai-upgrade-agent-2/.env | xargs)

# Enable upgrade write gate
az containerapp update -n aks-mcp -g $AZURE_RESOURCE_GROUP \
  --set-env-vars AKS_UPGRADE_ENABLE_WRITE="true"

# Enable remediation write gate (optional)
az containerapp update -n aks-mcp -g $AZURE_RESOURCE_GROUP \
  --set-env-vars AKS_REMEDIATION_ENABLE_WRITE="true"

# Verify gates are enabled
az containerapp show -n aks-mcp -g $AZURE_RESOURCE_GROUP --query "properties.template.containers[0].env[?name=='AKS_UPGRADE_ENABLE_WRITE'].value"
```

**Expected Output**:
```
"true"
```

**Warning**: Only enable write gates after:
- ✓ Comprehensive testing with read-only operations
- ✓ User approval to enable writes
- ✓ Audit logging configured
- ✓ Rollback procedures documented

### Step 8.2 — Configure Production Logging

**Purpose**: Set up detailed audit trail for compliance

**Command**:
```bash
source <(grep -v '^#' .azure/aks-ai-upgrade-agent-2/.env | xargs)

# Enable Application Insights integration
az containerapp update -n aks-mcp -g $AZURE_RESOURCE_GROUP \
  --enable-diagnostics

# Configure log retention
az monitor log-analytics workspace update \
  -g $AZURE_RESOURCE_GROUP \
  -n "log-*" \
  --retention-time 90  # 90 days retention
```

### Step 8.3 — Configure Monitoring and Alerts (Optional)

**Purpose**: Set up alerts for failures and anomalies

**Command**:
```bash
# Create alert rule for Container App failures
az monitor metrics alert create \
  --name "aks-mcp-errors" \
  --resource-group $AZURE_RESOURCE_GROUP \
  --resource /subscriptions/*/resourceGroups/*/providers/Microsoft.App/containerApps/aks-mcp \
  --condition "avg Exceptions > 10" \
  --window-size 5m \
  --description "Alert if MCP server errors exceed 10 per 5min" \
  --actions /subscriptions/*/resourceGroups/*/providers/microsoft.insights/actiongroups/default
```

## PHASE 9 — Documentation and Handoff (5 minutes)

### Step 9.1 — Document Configuration

**Purpose**: Record deployment specifics for operations team

**Command**:
```bash
# Generate deployment summary
cat > DEPLOYMENT_SUMMARY.md <<EOF
# AKS Upgrade Agent Deployment Summary

## Deployment Date
$(date)

## Azure Resources
- Subscription: $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_SUBSCRIPTION_ID | cut -d= -f2)
- Resource Group: $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2)
- Region: $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_LOCATION | cut -d= -f2)

## Deployed Services
- Foundry Agent: $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AGENT.*ENDPOINT | head -1)
- MCP Server: $(az containerapp show -n aks-mcp -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --query properties.configuration.ingress.fqdn -o tsv)/mcp

## Target Cluster
- Subscription: $TARGET_SUBSCRIPTION
- Resource Group: $TARGET_RESOURCE_GROUP
- Cluster: $TARGET_CLUSTER

## Write Gates Status
- AKS_UPGRADE_ENABLE_WRITE: $(az containerapp show -n aks-mcp -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --query "properties.template.containers[0].env[?name=='AKS_UPGRADE_ENABLE_WRITE'].value" -o tsv || echo "not set")
- AKS_REMEDIATION_ENABLE_WRITE: $(az containerapp show -n aks-mcp -g $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --query "properties.template.containers[0].env[?name=='AKS_REMEDIATION_ENABLE_WRITE'].value" -o tsv || echo "not set")

## Next Steps
1. Review deployment validation results
2. Run smoke tests: see 14-validation-and-smoke-tests.md
3. Enable write gates when approved: see 08.1 above
4. Monitor logs in Log Analytics / Application Insights
5. See troubleshooting guide: 15-troubleshooting.md
EOF

cat DEPLOYMENT_SUMMARY.md
```

### Step 9.2 — Verify All Documentation Links

**Purpose**: Ensure operations team has access to all runbooks

**Command**:
```bash
# Check all documentation files exist
ls -la docs/azure/ | grep "\.md$"

# Verify key files
test -f docs/azure/README.md && echo "✓ README exists"
test -f docs/azure/14-validation-and-smoke-tests.md && echo "✓ Validation guide exists"
test -f docs/azure/15-troubleshooting.md && echo "✓ Troubleshooting guide exists"
test -f docs/azure/16-rollback.md && echo "✓ Rollback guide exists"
test -f docs/azure/17-operations-and-monitoring.md && echo "✓ Operations guide exists"
```

## Rollback (If Deployment Fails)

If any phase fails critically:

```bash
# Destroy all resources (WARNING: irreversible)
azd down --purge

# Or selectively destroy:
az group delete -n $(cat .azure/aks-ai-upgrade-agent-2/.env | grep AZURE_RESOURCE_GROUP | cut -d= -f2) --yes
```

## Post-Deployment Verification Checklist

After completing all phases:

- [ ] `azd show` returns healthy status
- [ ] Agent responds to: `azd ai agent invoke "Hello"`
- [ ] MCP endpoint responds: `curl -X POST <endpoint>/mcp -d '{"jsonrpc":"2.0",...}'`
- [ ] Container App logs show no errors: `az containerapp logs show -n aks-mcp -g <rg>`
- [ ] Target cluster is reachable from MCP: `az aks command invoke -n <cluster> -g <rg> --command "kubectl get nodes"`
- [ ] Read-only assessment succeeds: `azd ai agent invoke "Assess cluster"`
- [ ] Write gates status matches plan (enabled or disabled)
- [ ] Logging is configured and receiving data
- [ ] RBAC roles are assigned to managed identities
- [ ] Documentation has been reviewed and is accessible

---

**For Issues**: See [15-troubleshooting.md](15-troubleshooting.md)  
**For Operations**: See [17-operations-and-monitoring.md](17-operations-and-monitoring.md)  
**For Rollback**: See [16-rollback.md](16-rollback.md)  

**Status**: Production POC  
**Last Updated**: 2026-09-10

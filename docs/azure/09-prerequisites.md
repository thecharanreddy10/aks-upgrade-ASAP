# 09 — Prerequisites

## Environment Requirements

Before deploying the AKS Upgrade Agent, verify that your environment meets all prerequisites.

| Requirement | Version | Mandatory | Purpose | Verification Command |
|-----------|---------|-----------|---------|----------------------|
| Azure Subscription | Any active | ✓ Yes | Cloud resource provisioning and billing | `az account list` |
| Azure CLI (az) | >= 2.57.0 | ✓ Yes | Azure resource management | `az --version` |
| Azure Developer CLI (azd) | >= 1.14.0 | ✓ Yes | Unified provisioning and deployment | `azd version` |
| Python | >= 3.11 (3.13 recommended) | ✓ Yes (for local dev) | Agent and MCP server runtime | `python --version` |
| Docker | >= 24.0 | ✓ Yes (for builds) | Container image builds | `docker --version` |
| kubectl | >= 1.27.0 | ✓ Yes (for testing) | Kubernetes cluster access | `kubectl version --client` |
| Git | >= 2.40.0 | ✓ Yes | Repository access | `git --version` |
| Node.js | >= 18.0 (for azd) | ✓ Yes (azd dependency) | Azure Developer CLI runtime | `node --version` |
| Terraform | >= 1.0 (if using) | ✗ No (optional IaC) | Infrastructure-as-code | `terraform --version` |
| Bicep | >= 0.16.0 (if using) | ✗ No (optional IaC) | Infrastructure-as-code | `az bicep version` |
| jq | >= 1.6 | ✗ No (for parsing JSON) | CLI output parsing | `jq --version` |

## Azure Resource Provider Registration

Ensure required Azure resource providers are registered in your subscription:

```bash
# Check if providers are registered
az provider show --namespace Microsoft.CognitiveServices --query "registrationState"
az provider show --namespace Microsoft.ContainerService --query "registrationState"
az provider show --namespace Microsoft.ContainerRegistry --query "registrationState"
az provider show --namespace Microsoft.App --query "registrationState"
az provider show --namespace Microsoft.OperationalInsights --query "registrationState"
az provider show --namespace Microsoft.Insights --query "registrationState"

# Register providers (if not registered)
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.ContainerService
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.Insights
```

## Azure Permissions Required

### Subscription Level

| Role | Purpose | For | Mandatory |
|------|---------|-----|-----------|
| Owner or Contributor | Provision all resources, assign RBAC roles | User deploying solution | ✓ Yes |
| User Access Administrator | Assign managed identity roles | User deploying solution | ✓ Yes (for RBAC) |

### Resource Group Level

| Role | Purpose | For | Mandatory |
|------|---------|-----|-----------|
| Contributor | Create/modify resources in RG | Deployment pipeline | ✓ Yes |
| Cognitive Services Contributor | Manage Cognitive Services/OpenAI | MCP Server identity | ✓ Yes |
| AcrPush | Push images to ACR | CI/CD build agent | ✓ Yes |

### Target AKS Cluster Level

| Role | Purpose | For | Mandatory |
|------|---------|-----|-----------|
| AKS Cluster User Role | Access cluster via kubectl/AKS Run Command | MCP Server identity | ✓ Yes |
| Azure Kubernetes Service RBAC Admin | Full cluster access (if needed) | Debug/troubleshoot | ✗ No |

## Quota Verification

Verify that your subscription has sufficient quota for required resources:

```bash
# Check vCPU quota (for Container App scaling)
az vm list-usage --query "[?name.value == 'standardDSv3Family']" -o table

# Check Cognitive Services quota
az cognitiveservices account create --check-name-availability --name "test-name" --kind CognitiveServices

# Check Container Registry quota
az acr check-usage --resource-group <rg> --name <registry>

# Check AKS quota
az container app list -g <rg>
```

## Regional Availability

The solution has been validated in:

| Region | Resource | Status |
|--------|----------|--------|
| eastus2 | All (Foundry, Cognitive Services, Container Apps) | ✓ Validated |
| eastus | All (Foundry, Cognitive Services, Container Apps) | ✓ Likely available |
| westus2 | All (Foundry, Cognitive Services, Container Apps) | ✓ Likely available |
| westus3 | Foundry Agent Service | ⚠ Check availability |

**Recommendation**: Use **eastus2** (validated deployment region) or verify regional availability before choosing alternate region.

## Local Development Setup

For local agent development and testing:

### Step 1: Install Core Tools

```bash
# macOS (using Homebrew)
brew install azure-cli python@3.13 docker kubectl git

# Windows (using Chocolatey)
choco install azure-cli python docker-desktop kubernetes-cli git

# Linux (Ubuntu/Debian)
sudo apt-get install -y azure-cli python3.13 docker.io kubectl git
```

### Step 2: Install Azure Developer CLI

```bash
# Windows
winget install microsoft.azd

# macOS
brew install azd

# Linux
curl -fsSL https://aka.ms/install-azd.sh | bash
```

### Step 3: Create Python Virtual Environment

```bash
cd src/aks-operations-mcp
python3.13 -m venv venv
source venv/bin/activate  # macOS/Linux
# or
.\venv\Scripts\activate   # Windows
```

### Step 4: Install Python Dependencies

```bash
# Install MCP server dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing

# Install agent dependencies
cd ../agent-framework-agent-with-foundry-toolbox-responses
pip install -r requirements.txt
```

### Step 5: Test MCP Server Locally

```bash
cd src/aks-operations-mcp
python main.py

# In another terminal, test MCP endpoint
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}'
```

### Step 6: Test Agent Locally

```bash
cd src/agent-framework-agent-with-foundry-toolbox-responses
azd ai agent run          # Runs agent on http://localhost:8088
# In another terminal:
azd ai agent invoke --local "Hello, what version is my AKS cluster?"
```

## Authentication Setup

### Option 1: User Authentication (Development)

```bash
# Login with your Azure account
az login

# Set default subscription
az account set --subscription <subscription-id>

# Verify login
az account show
```

### Option 2: Service Principal (CI/CD)

```bash
# Create service principal
az ad sp create-for-rbac --name "akd-upgrade-agent-sp" --role Contributor --scopes /subscriptions/<subscription-id>

# Output will show:
# {
#   "appId": "...",
#   "displayName": "akd-upgrade-agent-sp",
#   "password": "...",
#   "tenant": "..."
# }

# Set environment variables for CI/CD
export AZURE_CLIENT_ID="appId"
export AZURE_CLIENT_SECRET="password"
export AZURE_TENANT_ID="tenant"
export AZURE_SUBSCRIPTION_ID="subscription-id"

# Or in Azure DevOps/GitHub:
# Set as pipeline secrets or GitHub secrets
```

### Option 3: Workload Identity Federation (Recommended for CI/CD)

```bash
# Create federated credentials for GitHub
az identity federated-credential create \
  --name "github-akd-upgrade-agent" \
  --identity-name "agent-identity" \
  --resource-group "<rg>" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:org/repo:ref:refs/heads/main"

# Use AZURE_CLIENT_ID (identity client ID) in GitHub Actions
# GitHub Actions runtime provides OIDC token automatically
```

## Testing Prerequisites

### Unit Testing

```bash
# Install test dependencies
cd src/aks-operations-mcp
pip install pytest pytest-cov pytest-mock

# Run tests
pytest tests/ -v

# Generate coverage report
pytest tests/ --cov=tools --cov-report=html
```

### Integration Testing

```bash
# Requires:
# 1. Deployed MCP server (Container App endpoint)
# 2. Azure subscription with AKS cluster
# 3. Managed identity with AKS Cluster User role

# Set environment variables
export AZURE_SUBSCRIPTION_ID="..."
export AZURE_RESOURCE_GROUP="..."
export AZURE_TENANT_ID="..."

# Run integration tests
pytest tests/integration/ -v
```

### Smoke Testing (Post-Deployment)

```bash
# Use scripts from 14-validation-and-smoke-tests.md
# Requires:
# 1. Deployed agent (Foundry Agent Service)
# 2. Deployed MCP server (Container App)
# 3. Target AKS cluster reachable

./smoke-tests/01-auth-test.sh
./smoke-tests/02-infrastructure-test.sh
./smoke-tests/03-app-health-test.sh
./smoke-tests/04-agent-test.sh
```

## Pre-Deployment Checklist

Before running `azd provision` and `azd deploy`, verify:

- [ ] Azure CLI is installed and authenticated (`az account show` succeeds)
- [ ] Azure Developer CLI is installed (`azd version` succeeds)
- [ ] Docker is installed and running (`docker ps` succeeds)
- [ ] kubectl is installed (`kubectl version --client` succeeds)
- [ ] Python 3.11+ is installed (`python --version` succeeds)
- [ ] Azure subscription has sufficient quota (Container App, Cognitive Services, ACR)
- [ ] Azure resource providers are registered (see section above)
- [ ] User has Contributor + User Access Administrator roles on subscription
- [ ] Target AKS cluster exists and is reachable
- [ ] Target AKS cluster version is 1.27 or higher
- [ ] All required permissions are assigned to target subscription/cluster
- [ ] Environment variables are set (AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID)
- [ ] Repository is cloned locally (`git clone ...`)
- [ ] Python dependencies are installed (`pip install -r requirements.txt`)
- [ ] MCP server runs locally (`python main.py` succeeds)
- [ ] Agent runs locally (`azd ai agent run` succeeds)

## Troubleshooting Prerequisites

### Issue: `az login` fails

**Solution**:
```bash
# Clear cached credentials
az logout

# Login with device code
az login --use-device-code

# Or login interactively
az login
```

### Issue: `azd` command not found

**Solution**:
```bash
# Verify installation
azd version

# If not installed:
# Windows: winget install microsoft.azd
# macOS: brew install azd
# Linux: curl -fsSL https://aka.ms/install-azd.sh | bash
```

### Issue: Resource provider not registered

**Solution**:
```bash
# Register required providers
az provider register --namespace Microsoft.CognitiveServices
az provider register --namespace Microsoft.App

# Wait for registration (can take 10 minutes)
az provider show --namespace Microsoft.CognitiveServices --query "registrationState"
```

### Issue: Quota exceeded

**Solution**:
```bash
# Request quota increase via Portal or CLI
az quota request create \
  --resource-name "standard..." \
  --resource-provider "microsoft.compute" \
  --scopes "/subscriptions/<id>"
```

---

**Next**: [10-environment-configuration.md](10-environment-configuration.md) for configuration details  
**Status**: Production POC  
**Last Updated**: 2026-09-10

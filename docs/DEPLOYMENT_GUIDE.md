# AKS Upgrade Agent Deployment Guide

This guide deploys the complete AKS Upgrade Agent into a new Azure environment:

1. An existing target AKS cluster.
2. An AKS Operations MCP server in Azure Container Apps.
3. A Foundry Toolbox connected to the MCP server.
4. A Microsoft Foundry hosted agent deployed through Azure Developer CLI (`azd`).

The repository's `azure.yaml` manages the Foundry project and hosted agent. It does **not**
provision the target AKS cluster or deploy the MCP Container App. MCP deployment is a separate
container workflow described below.

## Architecture

```text
User
  -> Foundry hosted agent
  -> Foundry Toolbox
  -> AKS Operations MCP in Azure Container Apps
  -> target AKS cluster
```

The current MCP registry exposes **29 tools**. The list is defined in
`src/aks-operations-mcp/tools/registry.py` and is the source of truth for the MCP `tools/list`
response.

## Required Inputs

Prepare these values before deployment:

| Value | Description |
|---|---|
| Azure subscription | Subscription where Foundry, ACR, and Container Apps will run |
| Azure tenant | Microsoft Entra tenant used for login |
| Azure location | Region supporting the required Azure services |
| Foundry project | Existing project or one created by `azd provision` |
| Model deployment | Chat model available in the Foundry project |
| Target AKS subscription | Subscription containing the AKS cluster |
| Target AKS resource group | Resource group containing the AKS cluster |
| Target AKS cluster | Existing cluster to assess or upgrade |
| MCP resource group | Resource group for the MCP Container App and registry |
| MCP Container App name | For example, `aks-mcp` |
| MCP public URL | The `/mcp` endpoint exposed by the Container App |

The target AKS cluster must already exist. This project does not create an AKS cluster.

## Prerequisites

Install and authenticate the following tools on the deployment workstation:

- Azure CLI (`az`)
- Azure Developer CLI (`azd`)
- Docker, or an ACR remote-build workflow
- Python 3.11 or later
- `kubectl` for optional cluster validation
- Git

Sign in to both CLIs:

```powershell
az login
az account set --subscription <deployment-subscription-id>
azd auth login
```

Set the Foundry skill user agent for `azd` commands in the current PowerShell session:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
```

Check the tools:

```powershell
az version
azd version
python --version
docker version
```

## Clone and Inspect the Repository

```powershell
git clone <repository-url>
Set-Location <repository-directory>
git status --short
```

Do not deploy with unreviewed local changes. Confirm that these files exist:

- `azure.yaml`
- `src/agent-framework-agent-with-foundry-toolbox-responses/main.py`
- `src/agent-framework-agent-with-foundry-toolbox-responses/requirements.txt`
- `src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml`
- `src/aks-operations-mcp/Dockerfile`
- `src/aks-operations-mcp/main.py`
- `src/aks-operations-mcp/requirements.txt`
- `src/aks-operations-mcp/tools/registry.py`

## Configure the Deployment Environment

Create or select an `azd` environment:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd env new <environment-name>
azd env select <environment-name>
```

For an existing Foundry project, set its endpoint and model deployment. Use the actual values
for the selected subscription and project:

```powershell
azd env set AZURE_AI_PROJECT_ENDPOINT "https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "<model-deployment-name>"
azd env get-values
```

For a new Foundry project, `azd provision --no-prompt` can create the resources described by
the repository's `azure.yaml` and infrastructure configuration:

```powershell
azd provision --no-prompt
azd env get-values
```

Review the provisioned resources before continuing. Do not run `azd provision` if the project
endpoint and required Foundry resources already exist unless infrastructure changes are intended.

## Deploy the MCP Server

The MCP server is deployed independently from `azure.yaml`.

### 1. Create the MCP resource group and registry

Skip resource creation when they already exist:

```powershell
$mcpResourceGroup = "<mcp-resource-group>"
$location = "<azure-region>"
$registryName = "<globally-unique-acr-name>"

az group create --name $mcpResourceGroup --location $location
az acr create --name $registryName --resource-group $mcpResourceGroup --location $location --sku Basic
```

The registry name must be globally unique and contain only supported characters.

### 2. Build and push the MCP image

Run from the repository root:

```powershell
$tag = "aks-mcp-$(Get-Date -Format yyyyMMdd-HHmmss)"
az acr build `
  --registry $registryName `
  --image "aks-mcp:$tag" `
  --build-arg "SOURCE_REVISION=$tag" `
  ./src/aks-operations-mcp
```

The `SOURCE_REVISION` build argument is a cache key. It ensures a new image packages the current
registry instead of reusing a stale Docker layer.

Record the image digest printed by ACR. Prefer the immutable digest for production rollback.

### 3. Create the MCP managed identity

Create a user-assigned identity for the Container App:

```powershell
$identityName = "id-aks-mcp"
az identity create --name $identityName --resource-group $mcpResourceGroup --location $location
$identityId = az identity show --name $identityName --resource-group $mcpResourceGroup --query id -o tsv
$identityPrincipalId = az identity show --name $identityName --resource-group $mcpResourceGroup --query principalId -o tsv
```

Grant the identity permission to pull the MCP image from ACR. This is required when the
Container App uses the managed identity for registry authentication:

```powershell
$acrId = az acr show --name $registryName --resource-group $mcpResourceGroup --query id -o tsv

az role assignment create `
  --assignee-object-id $identityPrincipalId `
  --assignee-principal-type ServicePrincipal `
  --role AcrPull `
  --scope $acrId
```

Verify the assignment:

```powershell
az role assignment list `
  --assignee-object-id $identityPrincipalId `
  --scope $acrId `
  -o table
```

### 4. Grant the identity access to the target AKS cluster

This is a mandatory manual step. The MCP identity needs permission in the **target AKS
subscription**, which may differ from the deployment subscription.

```powershell
$targetSubscriptionId = "<target-aks-subscription-id>"
$targetResourceGroup = "<target-aks-resource-group>"
$clusterName = "<target-aks-cluster-name>"

$clusterId = "/subscriptions/$targetSubscriptionId/resourceGroups/$targetResourceGroup/providers/Microsoft.ContainerService/managedClusters/$clusterName"

az role assignment create `
  --assignee-object-id $identityPrincipalId `
  --assignee-principal-type ServicePrincipal `
  --role "Azure Kubernetes Service RBAC User" `
  --scope $clusterId
```

If the MCP identity requires additional access to perform cluster operations, grant `Reader`
and/or `Azure Kubernetes Service Contributor Role` at the target AKS resource scope:

```powershell
az role assignment create --assignee-object-id $identityPrincipalId --assignee-principal-type ServicePrincipal --role "Reader" --scope $clusterId
az role assignment create --assignee-object-id $identityPrincipalId --assignee-principal-type ServicePrincipal --role "Azure Kubernetes Service Contributor Role" --scope $clusterId
```

If the chosen AKS access path requires Run Command permissions, grant the least-privilege role
required by the cluster's configuration and verify it with the target cluster administrator. Do
not grant subscription Owner or Contributor as a shortcut.

Verify the assignment:

```powershell
az role assignment list --assignee-object-id $identityPrincipalId --scope $clusterId -o table
```

### 5. Create or update the MCP Container App

Create the Container App environment if necessary:

```powershell
$containerEnvName = "<container-app-environment>"
az containerapp env create `
  --name $containerEnvName `
  --resource-group $mcpResourceGroup `
  --location $location
```

Create the app using the image and managed identity:

```powershell
$acrLoginServer = az acr show --name $registryName --query loginServer -o tsv
$image = "$acrLoginServer/aks-mcp:$tag"

az containerapp create `
  --name aks-mcp `
  --resource-group $mcpResourceGroup `
  --environment $containerEnvName `
  --image $image `
  --target-port 80 `
  --ingress external `
  --min-replicas 1 `
  --max-replicas 10 `
  --user-assigned $identityId `
  --registry-server $acrLoginServer `
  --registry-identity $identityId `
  --env-vars `
    PORT=80 `
    AKS_REMEDIATION_ENABLE_WRITE=false `
    AKS_UPGRADE_ENABLE_WRITE=false
```

For an existing app, update only the image first:

```powershell
az containerapp update `
  --name aks-mcp `
  --resource-group $mcpResourceGroup `
  --image $image
```

Keep existing secrets, identity, ingress, scaling, and write-gate settings unless a deliberate
configuration change is required.

Get the MCP URL:

```powershell
$mcpHost = az containerapp show --name aks-mcp --resource-group $mcpResourceGroup --query properties.configuration.ingress.fqdn -o tsv
$mcpEndpoint = "https://$mcpHost/mcp"
$mcpEndpoint
```

## Configure the Foundry Toolbox

Edit `src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml` and replace
`server_url` with the new MCP endpoint. Keep `server_label: aks-ops` stable:

```yaml
tools:
  - type: mcp
    server_label: aks-ops
    server_url: "https://<mcp-host>/mcp"
    require_approval: "never"
```

Create a versioned Toolbox from the project root:

```powershell
$projectEndpoint = "https://<foundry-account>.services.ai.azure.com/api/projects/<project-name>"
azd ai toolbox create aks-agent-tools --from-file ./src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml --project-endpoint $projectEndpoint
```

Copy the versioned MCP endpoint printed by the command. Update the `TOOLBOX_ENDPOINT` value in
the `azure.yaml` agent service block to that endpoint. The Toolbox version is immutable; every
new MCP endpoint or tool signature requires a new Toolbox version and an agent redeployment.

## Deploy the Hosted Agent

Validate locally before deploying:

```powershell
python -m compileall src/agent-framework-agent-with-foundry-toolbox-responses
python -m pytest -q src/aks-operations-mcp/tests
```

Deploy only the hosted agent service:

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd deploy agent-framework-agent-with-foundry-toolbox-responses --no-prompt
```

Each successful deployment creates an immutable Foundry agent version. Record the version and
keep the previous active version available until smoke testing is complete.

## Post-Deployment Validation

### Verify the MCP Container App

```powershell
az containerapp show `
  --name aks-mcp `
  --resource-group $mcpResourceGroup `
  --query "{status:properties.runningStatus,revision:properties.latestReadyRevisionName,image:properties.template.containers[0].image}" `
  -o json
```

The status must be `Running` and the latest ready revision must be healthy.

### Verify the live MCP tool list

The MCP endpoint uses Streamable HTTP. Use an MCP-capable client or the repository's schema
verification scripts. The current registry should return **29 tools** and should not include
retired tools such as `aks_check_upgrade_compatibility` or `aks_plan_rbac_remediation`.

### Verify the hosted agent

```powershell
$env:AZURE_DEV_USER_AGENT = "microsoft_foundry_skill"
azd ai agent show agent-framework-agent-with-foundry-toolbox-responses --output json
azd ai agent invoke agent-framework-agent-with-foundry-toolbox-responses "List the MCP tools available to you and give the total count. Do not call any write tool."
```

The agent should be `active`, use the intended Toolbox version, and report 29 MCP tools. The
platform may also expose its own functions; those are not part of the MCP count.

### Read-only cluster smoke test

Use a real target cluster and run a read-only request first:

```text
Assess AKS upgrade readiness for <cluster>. Report blockers and warnings only. Do not execute
an upgrade or remediation.
```

Confirm that the agent calls read-only discovery and mandatory readiness tools and does not
perform writes.

## Write-Gate Configuration

Writes are disabled by default and should remain disabled for the first deployment:

- `AKS_UPGRADE_ENABLE_WRITE=false`
- `AKS_REMEDIATION_ENABLE_WRITE=false`

Only an authorized operator should enable writes:

```powershell
az containerapp update `
  --name aks-mcp `
  --resource-group $mcpResourceGroup `
  --set-env-vars AKS_UPGRADE_ENABLE_WRITE=true AKS_REMEDIATION_ENABLE_WRITE=true
```

Before enabling writes, verify the MCP identity, target cluster, approval workflow, backup plan,
maintenance window, and rollback plan. The agent's human approval policy is instruction-level;
the MCP server does not issue a cryptographic approval token.

## Upgrade and Remediation Safety

- Run assessment before proposing any upgrade.
- Use `check_mode=full` for real writes.
- Require explicit approval for the exact upgrade scope.
- Do not use generic CLI write tools as a shortcut around dedicated guardrails.
- Do not delete healthy storage to solve a design or data-migration problem.
- Do not automate CRD migration, operator upgrades, StorageClass migration, or application data migration.
- Verify the live cluster after every write.
- Treat failed or canceled Azure operations as terminal until an operator reviews them.

## Rollback

### MCP rollback

Deploy the previous immutable image digest:

```powershell
az containerapp update `
  --name aks-mcp `
  --resource-group $mcpResourceGroup `
  --image "<registry>.azurecr.io/aks-mcp@sha256:<previous-digest>"
```

Verify the new revision is healthy and receives 100% traffic.

### Agent rollback

Foundry agent versions are immutable. Keep the prior version reference and redeploy the known-good
source or use the Foundry deployment tooling to select the previous active version, according to
the current platform capabilities. Do not delete the previous version until the new deployment
has passed validation.

### Cluster rollback

AKS Kubernetes upgrades are not generally downgradable. Rollback means stopping further stages,
restoring application or configuration changes where possible, and following the cluster and
application disaster-recovery plan.

## Troubleshooting

| Symptom | Check |
|---|---|
| Agent cannot see tools | Confirm `TOOLBOX_ENDPOINT`, Toolbox version, MCP URL, and live `tools/list`. |
| MCP revision is unhealthy | Inspect Container App logs, image digest, managed identity, and required environment variables. |
| MCP receives authorization errors | Verify the managed identity has both `AcrPull` on the registry and the required role at the target AKS cluster scope. |
| Agent deployment fails | Run `azd ai agent doctor --output json`, inspect the project endpoint and model deployment, then retry after correction. |
| Tool count is unexpected | Compare the live `tools/list` response with `tools/registry.py`; rebuild with a unique `SOURCE_REVISION`. |
| Upgrade write is blocked | Confirm `AKS_UPGRADE_ENABLE_WRITE`, `check_mode=full`, explicit scope, readiness, and Azure permissions. |

## Deployment Completion Checklist

- [ ] Azure subscription and tenant selected
- [ ] Target AKS cluster identified and reachable
- [ ] Foundry project and model deployment available
- [ ] ACR and Container Apps environment created
- [ ] MCP image built and pushed with an immutable digest recorded
- [ ] MCP managed identity created
- [ ] MCP identity granted `AcrPull` on the container registry
- [ ] Target AKS permissions granted to the MCP identity
- [ ] MCP Container App healthy
- [ ] MCP endpoint returns exactly 29 tools
- [ ] Toolbox created and versioned
- [ ] `TOOLBOX_ENDPOINT` updated in `azure.yaml`
- [ ] Hosted agent deployed and active
- [ ] Agent smoke test confirms the intended Toolbox and tool count
- [ ] Write gates remain disabled until separately approved
- [ ] Rollback image and previous agent version recorded

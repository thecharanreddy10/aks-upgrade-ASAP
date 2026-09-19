# Current Deployment Recovery Snapshot

Captured read-only on 2026-09-19 before deploying local commit
`058ea4481be4b31d2ebd188a5aad017be4cd5bdf`.

This file contains no secret values. Do not replace the identifiers below with credentials or
secret-backed environment variable values.

## Azure context

| Setting | Value |
|---|---|
| Subscription | `bb0e2c9e-d7fb-45e4-92cf-654f380e6388` (`AZpractice - 801755-Demo`) |
| Tenant | `02a0a979-8c72-4fa4-bb66-e07b1d185b5b` |
| azd environment | `aks-ai-upgrade-agent-2` |
| Foundry resource group | `rg-agent-framework-agent-with-foundry-toolbox-responses-dev-526c3b27` |
| Foundry project | `agent-framework-agent-with-found` |
| Foundry project endpoint | `https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found` |

## Running deployment

### Foundry hosted agent

| Setting | Value |
|---|---|
| Name | `agent-framework-agent-with-foundry-toolbox-responses` |
| Version | `45` |
| Status at capture | `active` |
| Version ID | `agent-framework-agent-with-foundry-toolbox-responses:45` |
| Code content hash | `db6e170c97173d9e82cbc503ab4590b3324c7331e36c5d3037e69f326a7c309e` |
| Runtime | `python_3_13`, remote build, entry point `python main.py` |
| Resources | `0.5` CPU, `1Gi` memory |
| Protocol | Responses `2.0.0` |
| Model deployment | `gpt-5-mini` |
| Toolbox | `aks-agent-tools-v19:1` |

The unversioned Responses endpoint is:

```text
https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found/agents/agent-framework-agent-with-foundry-toolbox-responses/endpoint/protocols/openai/responses?api-version=v1
```

Foundry agent versions are immutable. The current CLI can inspect version `45`, but it does not
expose a command that promotes an old hosted-agent version back to the unversioned endpoint. The
practical recovery procedure is therefore to deploy the preserved source again, producing a new
version with the old behavior.

Source recovery point:

```text
158b087571443e5e19567fcaf529541f29ca9022 (origin/main at capture)
recovery/deployed-2026-09-19 (local recovery branch at the same commit)
```

This commit is the best available source recovery point for version `45`, but the Git commit and
Foundry content hash are not cryptographically linked in deployment metadata. Keep version `45`
and its content hash above as the verification reference.

### Foundry Toolbox

| Setting | Value |
|---|---|
| Name | `aks-agent-tools-v19` |
| Toolbox ID | `toolbox_d71718f9997573ec65676d6e230aab7f02d98237` |
| Version | `1` |
| Version ID | `toolbox_d71718f9997573ec65676d6e230aab7f02d98237:1` |
| Default version | `1` |
| MCP tool label | `aks-ops` |
| Approval mode | `never` |
| Backing MCP URL | `https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp` |

Versioned endpoint:

```text
https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found/toolboxes/aks-agent-tools-v19/versions/1/mcp?api-version=v1
```

Toolbox versions are immutable, and version `1` was the default at capture. Deploying agent code
does not replace this Toolbox. If its default is changed, restore it with:

```powershell
$env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
azd ai toolbox publish aks-agent-tools-v19 1 --no-prompt
```

### AKS operations MCP Container App

| Setting | Value |
|---|---|
| Resource group | `rg-aks_upgrd_agent` |
| Container App | `aks-mcp` |
| Location | `East US 2` |
| Status at capture | `Running`, `Succeeded`, healthy |
| Active revision | `aks-mcp--0000055` |
| Traffic | 100% to the active/latest revision |
| Revision mode | `Single` |
| Maximum inactive revisions | `0` |
| Image tag | `crccfxat3jn5lls.azurecr.io/aks-mcp:local-fresh-readiness-20260918` |
| Immutable image | `crccfxat3jn5lls.azurecr.io/aks-mcp@sha256:5cd5b4ecfde1edc29b5fed6e598d647bccb62934ef057baeb87dcbec4d8d8bc7` |
| Public MCP URL | `https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp` |
| Container | `main`, `0.5` CPU, `1Gi` memory |
| Scale | Minimum 1, maximum 10 replicas |
| Ingress | External, target port 80, transport Auto |
| Managed environment | `cae-ccfxat3jn5lls` |
| User-assigned identity | `id-aksMcp-ccfxat3jn5lls` |

The app retains no inactive revisions. After another deployment, revision `0000055` may no longer
be available to reactivate. The immutable ACR digest above is the reliable MCP recovery artifact.
The tag and digest were both present in ACR at capture.

Restore the MCP image without changing its existing secrets, identity, ingress, or scale settings:

```powershell
az account set --subscription bb0e2c9e-d7fb-45e4-92cf-654f380e6388
az containerapp update `
  --name aks-mcp `
  --resource-group rg-aks_upgrd_agent `
  --image crccfxat3jn5lls.azurecr.io/aks-mcp@sha256:5cd5b4ecfde1edc29b5fed6e598d647bccb62934ef057baeb87dcbec4d8d8bc7
```

Verify the restored MCP deployment:

```powershell
az containerapp show `
  --name aks-mcp `
  --resource-group rg-aks_upgrd_agent `
  --query "{status:properties.runningStatus,ready:properties.latestReadyRevisionName,image:properties.template.containers[0].image,traffic:properties.configuration.ingress.traffic}" `
  --output json
```

## Recommended deployment and recovery order

1. Leave Toolbox `aks-agent-tools-v19:1` unchanged. Its versioned endpoint isolates the agent from
   later Toolbox changes.
2. Deploy and verify the rolled-back MCP first if MCP code changed. Record its new image digest and
   revision before moving on.
3. Deploy the rolled-back hosted agent. This creates a new immutable Foundry agent version.
4. Smoke-test the agent and confirm it is using the intended Toolbox endpoint.
5. If the MCP fails, update `aks-mcp` back to the preserved digest above.
6. If the agent fails, use a separate Git worktree at commit `158b087` and run `azd deploy` from
   that worktree. Do not reset or overwrite the rollback worktree to perform recovery.

Example agent source recovery worktree:

```powershell
git worktree add ..\aks-ai-upgrade-agent-2-recovery 158b087571443e5e19567fcaf529541f29ca9022
Set-Location ..\aks-ai-upgrade-agent-2-recovery
$env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
azd deploy agent-framework-agent-with-foundry-toolbox-responses --no-prompt
azd ai agent show --output json
```

Before running that recovery deploy, ensure the recovery worktree resolves the same azd environment
and project endpoint recorded above. A new worktree may not carry ignored `.azure` environment
state; select or restore environment `aks-ai-upgrade-agent-2` explicitly if needed.

## Pre-redeploy checks

Run these immediately before changing any deployment and compare them with this snapshot:

```powershell
$env:AZURE_DEV_USER_AGENT = 'microsoft_foundry_skill'
azd ai agent show --output json
azd ai toolbox show aks-agent-tools-v19 --version 1 --output json --no-prompt
az containerapp show --name aks-mcp --resource-group rg-aks_upgrd_agent --output json
```

Do not delete agent version `45`, Toolbox version `1`, or the ACR manifest with digest
`sha256:5cd5b4ecfde1edc29b5fed6e598d647bccb62934ef057baeb87dcbec4d8d8bc7` until the rolled-back
deployment has passed validation.

## Rollback deployment result

Deployment completed successfully on 2026-09-19 from local commit
`058ea4481be4b31d2ebd188a5aad017be4cd5bdf`.

| Component | Deployed state |
|---|---|
| MCP image tag | `crccfxat3jn5lls.azurecr.io/aks-mcp:rollback-058ea44-20260919` |
| MCP image digest | `sha256:ff90919b000381063d035251f9628bab0491c69d84daf163b362013cfd7cda20` |
| ACR build | `ch27` |
| MCP revision | `aks-mcp--0000056` |
| MCP revision health | Healthy, provisioned, one replica, 100% traffic |
| Toolbox | Existing immutable `aks-agent-tools-v19:1`; no change required |
| Hosted agent | `agent-framework-agent-with-foundry-toolbox-responses:46` |
| Agent code content hash | `d86bc307cbcfb6d8e70140d027f86cac72df31a4492650b5001214c9bfc05114` |
| Agent status | Active |

Validation completed:

- All 317 MCP tests passed before deployment.
- The rollback agent entry point compiled successfully and installed dependencies were consistent.
- MCP revision logs showed successful HTTP 200 `tools/list` requests.
- Agent version `46` completed a read-only remote smoke test and listed AKS tools through Toolbox
   `aks-agent-tools-v19:1`.
- Smoke-test conversation: `conv_00e4bc73ab768d3200B3WPLCMDzs6pz8tpjT5BBToePP1A1fIo`.
- Smoke-test trace: `d5aa2e801dd104f4fa6c79d1c0dce9d8`.
- Evaluation-suite generation was explicitly deferred.

The pre-rollback recovery artifacts remain valid: agent source branch
`recovery/deployed-2026-09-19` and MCP digest
`sha256:5cd5b4ecfde1edc29b5fed6e598d647bccb62934ef057baeb87dcbec4d8d8bc7`.
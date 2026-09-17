# Consolidated Deployment and Test Procedure

## Purpose

This procedure prepares and validates the current AKS Upgrade Agent deployment without executing deployment or changing an AKS cluster. It is written for Windows PowerShell and uses the current `azure.yaml` boundary.

## 0. Non-Execution Rule

Stop before any command that provisions or deploys Azure resources. Do not run:

```powershell
azd up
azd provision
azd package
azd deploy
```

Do not enable AKS upgrade or remediation writes during this checkpoint.

## 1. Repository and Tooling Checks

From the repository root:

```powershell
$ErrorActionPreference = 'Stop'

az --version
azd version
python --version
git --version
docker --version
kubectl version --client

az account show
azd env list
git status --short
```

Expected result:

- Azure CLI, AZD, Python, Git, Docker, and kubectl are available.
- The intended Azure account and subscription are selected.
- The working tree changes are understood before packaging.
- No command above provisions or deploys resources.

## 2. Inspect the AZD Deployment Boundary

Confirm the current service map:

```powershell
Get-Content .\azure.yaml
azd env get-values
```

The current file deploys:

- the Foundry hosted agent service
- the Foundry project service

The AKS Operations MCP server is not declared as an `azure.yaml` service. Therefore, before deployment, verify that the configured `TOOLBOX_ENDPOINT` points to the intended existing Foundry Toolbox and MCP version. Do not assume `azd deploy` publishes the MCP server.

## 3. Local Agent Validation

Run these checks from the repository root:

```powershell
python -m py_compile .\src\agent-framework-agent-with-foundry-toolbox-responses\main.py .\src\agent-framework-agent-with-foundry-toolbox-responses\context_diagnostics.py
python -m compileall -q .\src\agent-framework-agent-with-foundry-toolbox-responses
```

Confirm the source contains:

- `ContextDiagnosticsMiddleware`
- `default_options={"store": False}`
- the reduced agent instruction payload
- the configured `FoundryToolbox` endpoint path

The diagnostics middleware must remain measurement-only. It must not log message bodies, tool arguments, tool results, or credentials.

## 4. MCP Unit and Schema Validation

Create or activate a test environment, then run:

```powershell
Push-Location .\src\aks-operations-mcp
python -m pip install -r .\requirements.txt
python -m pip install -r .\requirements-dev.txt
python -m pytest -q
Pop-Location
```

Run the focused safety and schema checks:

```powershell
Push-Location .\src\aks-operations-mcp
python -m pytest -q tests\test_upgrade_execution.py tests\test_upgrade_readiness_validations.py tests\test_registry.py tests\test_server_side_remediation_approval.py
Pop-Location

$env:PYTHONPATH = (Resolve-Path .\src\aks-operations-mcp)
python .\verify_schema.py
```

Expected result:

- The full MCP suite passes.
- `aks_execute_confirmed_upgrade` exposes `confirmed_scope` and its required authorization fields.
- Tests confirm explicit confirmation, write gates, full-check mode, scope enforcement, and no speculative writes.

## 5. Docker Build Checks Without Push

Only run these if Docker Desktop is available and a local image build is desired. These commands build locally and do not push or deploy:

```powershell
docker build --pull -t aks-upgrade-agent-local .\src\agent-framework-agent-with-foundry-toolbox-responses
docker build --pull -t aks-mcp-local .\src\aks-operations-mcp
```

Optional image checks:

```powershell
docker image inspect aks-upgrade-agent-local
 docker image inspect aks-mcp-local
```

The agent image should expose port `8088`; the MCP image should expose port `80` and retain its Azure CLI dependency for controlled `aks_az_*` tools.

## 6. Configuration Review Before Approval

Review the effective AZD environment without printing secrets into logs:

```powershell
azd env get-values | Select-String 'AZURE_AI_MODEL_DEPLOYMENT_NAME|FOUNDRY|TOOLBOX|AKS_.*WRITE|RESOURCE_GROUP|LOCATION|SUBSCRIPTION'
```

Confirm:

- `AZURE_AI_MODEL_DEPLOYMENT_NAME` is the intended deployment.
- The Foundry project endpoint is the intended project.
- `TOOLBOX_ENDPOINT` is current and points to the expected MCP toolbox version.
- `AKS_UPGRADE_ENABLE_WRITE` is disabled or unset for initial hosted validation.
- `AKS_REMEDIATION_ENABLE_WRITE` is disabled or unset for initial hosted validation.
- No credentials, tokens, or secret values are committed or pasted into reports.

## 7. Approval Gate

Do not proceed to Azure validation or deployment until the deployment plan has been reviewed and approved. The approval must cover:

- target subscription and region
- Foundry project and model deployment
- existing MCP Toolbox endpoint
- whether infrastructure provisioning is required
- initial read-only validation scope

After approval, run the repository's Azure pre-deployment validation. Only after validation succeeds may the deployment operator choose the appropriate AZD command. This procedure itself does not execute that command.

## 8. Post-Deployment Read-Only Test Procedure

Run these tests only after a separately approved deployment:

1. Confirm the hosted agent version and health.
2. Confirm the agent can discover the expected MCP tools through Foundry Toolbox.
3. Submit a read-only cluster inventory or readiness request.
4. Verify no write or remediation tool is called during assessment.
5. Verify diagnostics logs report system, history, current-input, tool-call, tool-result, and estimated-token metrics without body content.
6. Verify the response reports evidence and blockers without claiming an upgrade.
7. Verify the write gates remain disabled.
8. Verify MCP server and Foundry logs contain no credentials or raw user/tool payloads.

## 9. Optional Live Write Tests

These are separate from deployment smoke testing and require explicit approval after read-only validation. They are intentionally not run here.

For a future control-plane-only test:

- use a maintenance-approved target version
- require explicit approval for that exact target and scope
- pass `confirmed_scope="control_plane_only"`
- pass `is_user_confirmed=true`
- require `check_mode="full"`
- enable the upgrade write gate only for the test window
- poll `aks_get_upgrade_execution_status`
- verify the control plane reaches the target and node pools are not modified

For a future complete-cluster test, independently approve the complete scope and verify fresh node-pool `SUPPORTED` evidence before any node-pool write.

## 10. Evidence to Record

Record only non-sensitive evidence:

- commit or working-tree identifier
- local test command and pass count
- agent version and deployment identifier
- MCP toolbox version and tool-list result
- diagnostics metric summaries
- readiness result and blocker/warning counts
- write-gate state
- final verification state

Do not record raw prompts, conversation history, tool arguments, tool results, access tokens, or connection strings containing secrets.

## Completion Criteria for This Preparation Phase

This phase is complete when:

- `.azure/deployment-plan.md` is reviewed and approved for later validation.
- Local agent compilation succeeds.
- The MCP full and focused test suites pass.
- The AZD service boundary and MCP dependency are understood.
- Configuration and write-gate settings are reviewed without exposing secrets.
- No Azure resource is provisioned or deployed.
- No Memory or history-compaction change is introduced.

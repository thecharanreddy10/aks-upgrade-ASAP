# AKS Upgrade Agent POC

> **Source control:** this repository is hosted on Azure DevOps at `AISolutions-Virtusa/AKS-Upgrade-Agent`.

## Overview

This repository contains a validated proof-of-concept **AI-powered AKS Upgrade Agent**. The agent is a **Foundry hosted agent** built with the [Agent Framework](https://github.com/microsoft/agent-framework), consuming a **Foundry Toolbox** that exposes the **AKS Operations MCP** server's tools over MCP. The agent assesses AKS upgrade readiness, presents an upgrade plan, requires explicit human approval, and executes approved upgrades asynchronously through MCP tools.

## Problem Statement

Upgrading an AKS cluster (control plane and node pools) safely requires checking for upgrade blockers (unhealthy nodes/pods, PodDisruptionBudget constraints, storage issues, deprecated Kubernetes APIs) before executing a long-running, potentially disruptive operation. Doing this manually is error-prone and easy to rush. This POC automates the assessment and staged execution while keeping a human in the approval loop.

## POC Goals

The POC is an AI-powered AKS Upgrade Agent that:

- assesses AKS upgrade readiness
- identifies upgrade blockers and warnings
- prepares an upgrade plan
- requires explicit human approval before upgrade execution
- executes approved AKS upgrades through MCP tools
- uses asynchronous Azure long-running-operation handling
- polls execution status
- advances through control-plane and node-pool stages
- performs final post-upgrade verification

## Architecture

```
User request
    â”‚
    â–¼
Foundry Agent (AKS Upgrade Operations Agent)
    â”‚  MCP over Foundry Toolbox
    â–¼
AKS Operations MCP (Azure Container Apps)
    â”‚  Azure SDK (ContainerServiceClient, AKS run command, Kubernetes API)
    â–¼
Target AKS Cluster
```

## Components

**Agent**
- Foundry hosted agent (source: [`src/agent-framework-agent-with-foundry-toolbox-responses`](src/agent-framework-agent-with-foundry-toolbox-responses))
- Uses Foundry Toolbox for tool discovery
- Current deployed agent version: **v47**

**MCP**
- AKS Operations MCP server (source: [`src/aks-operations-mcp`](src/aks-operations-mcp))
- Hosted in Azure Container Apps
- Current deployed revision: **aks-mcp--0000058**
- MCP endpoint: `https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp`
- Current MCP registry: **29 tools**
- Exposes read-only assessment/discovery tools and explicit write/upgrade tools

> Deployment versions are point-in-time values and will change after future deployments.

## End-to-End Workflow

```
User request
    â†“
Read-only assessment
    â†“
Azure upgrade-profile discovery
    â†“
Mandatory readiness checks
    â†“
Upgrade plan presented
    â†“
Explicit human approval
    â†“
Asynchronous upgrade submission
    â†“
Immediate in_progress response
    â†“
Status polling
    â†“
Stage advancement
    â†“
Node-pool evidence refresh
    â†“
Explicit approval for node-pool operation when required
    â†“
Final verification
```

The asynchronous design was introduced specifically to avoid keeping an MCP request open while Azure performs a long-running AKS upgrade operation.

## Read-Only Assessment

Before any write is considered, the agent operates strictly in a read-only assessment mode: gathering cluster/node-pool state, authoritative Azure upgrade-profile data, and mandatory readiness results. No write tool is invoked during assessment.

## Upgrade Readiness Checks

The POC treats these as **mandatory** upgrade-readiness checks that must pass (or have their blockers surfaced) before upgrade execution:

- node health
- pod health
- PodDisruptionBudget (PDB) health
- persistent storage / PV / PVC health
- deprecated Kubernetes API checks

In addition, four checks are **advisory (optional)** rather than mandatory blockers, and are only run on explicit user request:

- Cerebral Plus single-replica workloads (`aks_check_single_replica_services`)
- SIT operator health/readiness (`aks_check_operator_health`)
- AKS User node-pool Max Surge (`aks_check_node_pool_surge`)
- Critical system PriorityClass (`aks_check_priority_class`)

A `WARNING` from an optional check is a recommendation, not an automatic upgrade blocker, and does not count as a validation failure.

## Human Approval Model

Explicit human approval is currently an **agent/instruction-level workflow control**, not a cryptographically trusted server-side approval token. There is no application-level approval token issued or validated by the MCP server for upgrade or remediation operations.

The agent's instructions require:

- The upgrade-readiness assessment to run before any upgrade is proposed.
- The plan (current version, target version, control-plane/node-pool support status, proposed scope, blockers/warnings) to be presented to the user.
- An explicit, unambiguous user approval statement referring to the specific proposed upgrade before `aks_execute_confirmed_upgrade` is called.
- Ambiguous statements (e.g. "okay", "looks good") are never treated as approval.
- The write gate being enabled, or the write tool merely being available, is never treated as approval.

## Async Upgrade Execution

- `aks_execute_confirmed_upgrade` submits at most one Azure long-running operation per call.
- It returns without waiting for the Azure operation to finish.
- The agent uses `aks_get_upgrade_execution_status` to observe live execution state.
- Once the current stage reaches its target version and `Succeeded` provisioning state, the coordinator can be called again to advance to the next stage.
- No `poller.result()` is used by the async coordinator â€” it does not block on the Azure operation.
- Existing Azure provisioning state is checked to avoid duplicate submissions.
- Active execution tracking (an in-process lock keyed by cluster/pool) is **process-local**.
- Process-local protection is **not** cross-replica distributed locking â€” it does not guard against concurrent submissions from multiple MCP server replicas or processes.
- `Failed`/`Canceled` terminal states do not trigger speculative automatic retries; the coordinator reports the terminal state and stops.

## Control-Plane Upgrade Flow

1. Fresh discovery of current control-plane version and authoritative Azure upgrade-profile evidence.
2. Mandatory readiness checks run before the write.
3. On explicit approval with `confirmed_scope=control_plane_only` (or `complete_cluster`), the coordinator submits the control-plane upgrade and returns `in_progress`.
4. Status polling via `aks_get_upgrade_execution_status` observes `Upgrading` â†’ `Succeeded`.
5. `control_plane_only` never expands into node-pool execution â€” no node pool is touched regardless of profile state.

## Node-Pool Upgrade Flow

Node-pool execution is staged **after** control-plane completion, and only under a `complete_cluster` workflow:

- Node-pool Azure upgrade-profile evidence is refreshed only after the control-plane target is observed.
- The target version must be explicitly `SUPPORTED` for the node pool from fresh Azure evidence; unsupported or insufficient-evidence pools are not modified.
- Eligible node pools are upgraded sequentially.
- Node-pool provisioning state is polled the same way as the control plane.
- Final node-pool versions are verified after completion.

## Safety and Guardrails

- Read-only assessment before any execution
- `AKS_UPGRADE_ENABLE_WRITE` write gate (must be `true` for real writes)
- `check_mode=full` required for real writes
- Target-version validation (`major.minor[.patch]`)
- Authoritative Azure upgrade-profile validation (not a hardcoded version list)
- Mandatory readiness validation before submission
- Explicit `confirmed_scope` validation (`control_plane_only` vs `complete_cluster`)
- Node-pool execution requires supported/fresh Azure upgrade-profile evidence
- In-progress state checks to avoid duplicate submissions
- Terminal failure handling (`Failed`/`Canceled` reported, not retried automatically)
- Post-upgrade verification against live Azure state
- Explicit human approval enforced through agent instructions (not a server-side trusted token â€” see [Human Approval Model](#human-approval-model))

Remediation tools (PDB, pods, node, storage, deprecated APIs) share an analogous guardrail model: `dry_run=true` by default, explicit `dry_run=false` + `check_mode=full` + `AKS_REMEDIATION_ENABLE_WRITE=true` required for real writes, protected namespaces remain blocked, and destructive remediations require an explicit destructive-operation confirmation flag. See [src/aks-operations-mcp/README.md](src/aks-operations-mcp/README.md) for the full tool-level guardrail list.

## PDB and Storage Blocker Detection

The POC is designed to detect:

- PDB disruption/eviction constraints that could block or delay AKS node draining during upgrades
- persistent-volume/storage capacity, provisioning, attachment, or related problems that can prevent replacement/database pods from becoming healthy

Not every storage event automatically blocks an upgrade. Results are distinguished as:

- **blocker** â€” prevents/should prevent upgrade execution
- **warning** â€” a smoothness/risk concern that does not itself stop execution
- **transient event/anomaly** â€” observed but not treated as a blocker or warning

## Post-Upgrade Verification

After a control-plane or node-pool stage reaches `Succeeded`, the agent verifies the resulting version and provisioning state against live Azure data via `aks_get_upgrade_execution_status` before reporting completion or advancing to the next stage.

## Deployment Architecture

- **Agent:** Foundry hosted agent, connected to Toolbox `aks-agent-tools-v19:1`, using `FoundryChatClient` over the Responses protocol.
- **MCP:** AKS Operations MCP server hosted in Azure Container Apps, reached by the agent via the toolbox's MCP endpoint (`TOOLBOX_ENDPOINT`) or directly via `AKS_MCP_ENDPOINT`.

The agent uses `FoundryChatClient` from the Agent Framework to create an OpenAI-compatible Responses client. It connects to the toolbox's MCP endpoint via `FoundryToolbox` â€” a thin convenience wrapper over `MCPStreamableHTTPTool` that authenticates every request with the credential and forwards the platform per-request call-id â€” which discovers and invokes the toolbox's tools over MCP at runtime. `FoundryToolbox` resolves the endpoint from the `TOOLBOX_ENDPOINT` environment variable. If that variable isn't set, it builds the endpoint from `FOUNDRY_PROJECT_ENDPOINT` and `TOOLBOX_NAME`.

See [main.py](src/agent-framework-agent-with-foundry-toolbox-responses/main.py) for the full implementation.

### Current deployment snapshot

The current deployment is active and has been verified read-only:

- Foundry agent **v47** is active and connected to Toolbox `aks-agent-tools-v19:1`.
- MCP Container App revision **aks-mcp--0000058** is healthy and running.
- `tools/list` returns HTTP 200 and exposes **29 tools**.
- The upgrade and remediation write gates remain controlled by MCP environment settings.

## Validation / Test Results

Latest repository validation:

- Full MCP test suite: passed
- Focused registry and async tests: passed
- Agent `py_compile`: passed
- Agent `compileall`: passed
- `git diff --check`: passed

These are automated unit/static checks. The live MCP deployment currently reports 29 tools, and the hosted agent is active on version 47 using Toolbox `aks-agent-tools-v19:1`.

The live Azure upgrade tests described below were performed manually against a real cluster and are not part of the automated unit suite.

### Real end-to-end validation (live AKS cluster)

Initial live state:
- control plane `1.35.2`
- `nodepool1` `1.35.1`

**Control-plane test:**
- Approved target: `1.35.3`, scope: `control_plane_only`
- Async submission returned `in_progress`
- Status polling showed `Upgrading`
- Control plane eventually reached `1.35.3` / `Succeeded`
- `nodepool1` remained `1.35.1` (scope correctly did not expand)

**Node-pool test:**
- Refreshed Azure upgrade-profile evidence showed `nodepool1` `1.35.3` as `SUPPORTED`
- Explicit approval obtained
- `nodepool1` `1.35.1` â†’ `1.35.3`, async write accepted
- Provisioning state reported `Upgrading`
- `nodepool1` eventually reached `1.35.3` / `Succeeded`

**Final validated state:**
- control plane: `1.35.3` / `Succeeded`
- `nodepool1`: `1.35.3` / `Succeeded`

## Current Limitations

The following are **not** currently implemented as dedicated features:

- Automatic 1.30 â†’ LTS migration
- Automatic LTS support-plan enablement
- Production-grade distributed execution locking (current protection is process-local only â€” see [Async Upgrade Execution](#async-upgrade-execution))
- A trusted, cryptographic human-approval token mechanism (approval is currently an agent/instruction-level control â€” see [Human Approval Model](#human-approval-model))

## Future Enhancements

- Unsupported-LTS to supported-LTS upgrade planning
- LTS support-plan validation/configuration
- Distributed idempotency/locking across MCP replicas
- Trusted server-side approval mechanism
- Stronger persistent execution state (beyond process-local tracking)
- MCP Tasks/background execution for production-scale long-running workflows

## How to Run / Deploy

### Option 1: Azure Developer CLI (`azd`)

#### Prerequisites

1. **Azure Developer CLI (`azd`)** â€” [Install azd](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) (1.25 or later)
2. Install the unified Foundry CLI extension bundle (provides `azd ai agent`, `connection`, `inspector`, `project`, `routine`, `skill`, and `toolbox`):
   ```bash
   # If you previously installed individual extensions, uninstall them first:
   #   azd ext uninstall azure.ai.agents
   #   azd ext uninstall azure.ai.toolboxes
   azd ext install microsoft.foundry
   ```
3. Authenticate:
   ```bash
   azd auth login
   ```

#### Initialize the agent project

No cloning required. Create a new folder and initialize from the manifest:

```bash
mkdir my-toolbox-agent && cd my-toolbox-agent

azd ai agent init -m https://github.com/microsoft-foundry/foundry-samples/blob/main/samples/python/hosted-agents/agent-framework/responses/04-foundry-toolbox/azure.yaml
```

Follow the prompts to configure your Foundry project and model deployment. If you don't have an existing Foundry project, `azd ai agent init` will guide you through creating one. Initializing also sets the selected project as the active project for the `azd ai` commands that follow.

#### Create the toolbox with `azd ai`

> [!TIP]
> If you use GitHub Copilot for Azure to scaffold a hosted agent that consumes this toolbox, the following skill references describe the same endpoint contract (env var, headers, MCP protocol, citation patterns, and troubleshooting) that the agent must implement:
>
> - [Toolbox reference](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/toolbox-reference.md) â€” endpoint format, MCP protocol, OAuth consent handling, citation patterns, and troubleshooting.
> - [Use toolbox in a hosted agent](https://github.com/microsoft/GitHub-Copilot-for-Azure/blob/main/plugin/skills/microsoft-foundry/foundry-agent/create/references/use-toolbox-in-hosted-agent.md) â€” endpoint resolution, env-var contract, payload shape, code integration patterns, and tracing.

The agent reads the toolbox's MCP endpoint from `TOOLBOX_ENDPOINT`. This project uses the existing
`aks-agent-tools-v19:1` Toolbox version. For a new environment, create a toolbox from the bundled
[`toolbox.yaml`](src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml):

```bash
azd ai toolbox create aks-agent-tools --from-file ./src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml --project-endpoint https://<account>.services.ai.azure.com/api/projects/<project>
```

The first version becomes the default automatically. Use `azd ai toolbox list`, `azd ai toolbox show aks-agent-tools`, and `azd ai toolbox version list aks-agent-tools` to inspect, and `azd ai toolbox delete aks-agent-tools --force` to remove it.

To stage incremental changes safely, use `azd ai toolbox connection add/remove` and `azd ai toolbox skill add/list/remove`; each creates a new toolbox version that carries forward existing connections and skills but **doesn't** change the default. Promote a version with `azd ai toolbox publish aks-agent-tools <version>` when you're ready to make it active.

`azd ai toolbox create` prints the toolbox's versioned MCP endpoint. Copy that endpoint and store it in your `azd` environment so the agent connects to it:

```bash
azd env set TOOLBOX_ENDPOINT "https://<account>.services.ai.azure.com/api/projects/<project>/toolboxes/aks-agent-tools/versions/1/mcp?api-version=v1"
```

#### Provision Azure resources (if needed)

If you don't already have a Foundry project and model deployment:

```bash
azd provision
```

#### Run the agent locally

```bash
azd ai agent run
```

The agent host will start on `http://localhost:8088`.

#### Invoke the local agent

In a separate terminal, from the project directory:

```bash
azd ai agent invoke --local "What tools do you have?"
```

#### Deploy to Foundry

Once tested locally, deploy to Microsoft Foundry:

```bash
azd deploy
```

For the full deployment guide, see [Deploy a hosted agent](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent).

#### Invoke the deployed agent

```bash
azd ai agent invoke "What tools do you have?"
```

### Option 2: VS Code (Foundry Toolkit)

#### Prerequisites

1. **VS Code** with the **[Foundry Toolkit](https://marketplace.visualstudio.com/items?itemName=ms-windows-ai-studio.windows-ai-studio)** extension installed.
2. For debugging Python in VS Code, install the **[Python](https://marketplace.visualstudio.com/items?itemName=ms-python.python)** extension pack.
3. The `aks-agent-tools` toolbox must exist in your Foundry project. Create it from the bundled [`toolbox.yaml`](src/agent-framework-agent-with-foundry-toolbox-responses/toolbox.yaml) or in the Foundry portal before you run the agent.

#### Set up the Python virtual environment

- Open the Command Palette (`Ctrl+Shift+P`) and run **Python: Create Environment...** to create a virtual environment in the workspace (or **Python: Select Interpreter** to use an existing one).
- Install dependencies in the virtual environment:
  ```bash
  pip install uv
  uv pip install -r requirements.txt
  ```

#### Run and debug the agent

Press **F5** to start the agent. The agent starts and the **Agent Inspector** opens automatically. Chat with the agent in the Inspector.

#### Or run manually, then open the Inspector

1. Set the required environment variables and sign in to Azure with the Azure CLI (`az login`).
2. Start the agent: `python main.py` (listens on `http://localhost:8088`).
3. Command Palette (`Ctrl+Shift+P`) â†’ **Foundry Toolkit: Open Agent Inspector**, then send a message to test.

#### Deploy to Foundry

1. Open the Command Palette (`Ctrl+Shift+P`) and run **Foundry Toolkit: Deploy Hosted Agent**. The extension opens a **Deploy Hosted Agent** wizard and reads `agent.yaml` to auto-populate settings.
2. If prompted, complete **Foundry Project Setup** to select subscription and project.
3. On the **Basics** tab, choose deployment method (**Code** or **Container**) and confirm the agent name.
4. On **Review + Deploy**, confirm runtime details, pick **CPU and Memory** size, and click **Deploy**.
5. After deployment, invoke the agent in the Agent Playground and stream live logs from the **Logs** tab.

## Repository Structure

```
src/
  agent-framework-agent-with-foundry-toolbox-responses/   # Foundry hosted agent (AKS Upgrade Operations Agent)
    main.py            # Agent instructions and Foundry/toolbox wiring
    toolbox.yaml        # Toolbox definition pointing at the AKS Operations MCP endpoint
  aks-operations-mcp/                                     # AKS Operations MCP server
    tools/               # Discovery, validation, upgrade, and remediation tool implementations
    tests/               # Automated MCP test suite
    function_app.py     # Azure Functions entrypoint for remote hosting
```

## Troubleshooting

### A single failing MCP source can fail the whole agent

A toolbox aggregates every tool source behind one MCP endpoint. If **any** referenced MCP server fails while the toolbox enumerates tools (`tools/list`), the toolbox fails the entire enumeration, so the agent can't load its tools and every request returns an error (HTTP 500) until that source recovers.

For example, a flaky third-party MCP source can intermittently return `HTTP 502 (Bad Gateway)` during enumeration, which surfaces as:

```
tools/list failed for 1 tool source(s), succeeded for 5 tool source(s)
{"errors":[{"name":"<server_label>","type":"mcp","error":{"code":"HTTP_502", ...}}]}
```

This is an upstream/service hiccup, not a problem with the agent code. Mitigations:

- Retry the request â€” these failures are usually transient.
- If a source is persistently unavailable, temporarily remove its tool entry (and connection) from `toolbox.yaml`, recreate the toolbox, and update `TOOLBOX_ENDPOINT`.
- Inspect deployed agent logs with `azd ai agent monitor` to identify which source failed.

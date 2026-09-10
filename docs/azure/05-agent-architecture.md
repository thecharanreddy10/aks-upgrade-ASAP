# 05 — Agent Architecture

## Foundry Hosted Agent Design

### Agent Overview

The AKS Upgrade Agent is a **Foundry hosted agent** — a containerized AI agent that runs in Azure's Foundry Agent Service with integrated observability, scaling, and lifecycle management.

| Aspect | Value |
|--------|-------|
| **Type** | Foundry Hosted Agent |
| **Framework** | Agent Framework (agent-framework-foundry) |
| **Language** | Python 3.13 |
| **Model** | gpt-5-mini (Azure OpenAI) |
| **Protocol** | Responses (Foundry protocol) |
| **Runtime** | Managed container (Azure Foundry Agent Service) |
| **Configuration** | azure.yaml + environment variables |
| **Entry Point** | `src/agent-framework-agent-with-foundry-toolbox-responses/main.py` |
| **Container Image** | Multi-stage Docker build (bytecode precompilation for cold starts) |

### Agent Execution Flow

```
┌─────────────┐
│  User Chat  │
└──────┬──────┘
       │ POST /api/agents/*/invoke
       ▼
┌─────────────────────────────────┐
│ Foundry Agent Service Container │
│ ─────────────────────────────── │
│ • Start Python main.py          │
│ • Load instructions             │
│ • Create FoundryAgent           │
│ • Connect FoundryChatClient     │
│ • Setup credentials             │
└──────┬──────────────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Agent Main Loop          │
├──────────────────────────┤
│ 1. system_prompt + user  │
│    message              │
│ 2. LLM reasoning        │
│ 3. Tool decision        │
│ 4. MCP call (if needed) │
│ 5. Parse result         │
│ 6. LLM next step        │
│ 7. Loop or return       │
└──────────────────────────┘
       │
       ▼
┌──────────────────────────┐
│ Return Completion        │
│ • Final response text    │
│ • Tool invocation log    │
│ • Status                 │
└──────────────────────────┘
```

### Core Components

#### 1. Main Agent Class (Agent Framework)

**File**: `src/agent-framework-agent-with-foundry-toolbox-responses/main.py`

```python
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer

client = FoundryChatClient(
    project_endpoint=FOUNDRY_PROJECT_ENDPOINT,  # e.g., https://cog-*.services.ai.azure.com/api/projects/...
    model=AZURE_AI_MODEL_DEPLOYMENT_NAME,       # e.g., "gpt-5-mini"
    credential=DefaultAzureCredential()           # Managed identity auth
)

agent = Agent(
    client=client,
    instructions="""[Large system prompt with full agent behavior]"""
)

# Host agent over Responses protocol
server = ResponsesHostServer(agent)
server.run()
```

**Responsibilities**:
- Initialize credential (managed identity)
- Create LLM client (gpt-5-mini)
- Load system instructions
- Expose Responses endpoint (for Foundry invocation)

#### 2. System Instructions (Agent Behavior Policy)

**Location**: Hardcoded in `main.py` (lines 57-171+)

**Categories**:

1. **ASSESSMENT MODE** — Read-only discovery and validation
   - Use only read-only MCP tools
   - Never call write tools during assessment
   - Report blockers, warnings, recommendations
   - Stop after assessment

2. **REMEDIATION AUTHORIZATION** — Explicit approval for fixes
   - Current user request explicitly asking to fix/remediate = authorization
   - Do not ask for second approval or create dry-run workflow
   - Separate approval required for each remediation action
   - Remediate only identified workload unless broader scope explicitly requested

3. **REMEDIATION MODE** — Execute approved fix
   - Investigate first (read tools)
   - Call MCP write tool with `check_mode="full"`
   - Preserve safety controls (write gates, scope enforcement)
   - Verify result using read tools
   - Report actual result (never claim success without verification)

4. **UPGRADE APPROVAL POLICY** — Explicit user confirmation required
   - Never execute without explicit user approval of current plan
   - Approval must clearly refer to specific upgrade being proposed
   - Examples of valid approval:
     - "Yes, proceed with the upgrade to 1.35.1"
     - "I approve the control-plane upgrade to 1.35.1"
   - Examples of INVALID approval:
     - "okay", "looks good", "fine", "go ahead" (ambiguous)
     - Approval from earlier conversation (must be current)
     - Write tool availability or previous readiness assessment

5. **OPTIONAL UPGRADE-SMOOTHNESS VALIDATIONS**
   - Four optional checks (separate from mandatory readiness):
     - Cerebral Plus single-replica workloads
     - SIT operator health/readiness
     - AKS User node-pool Max Surge
     - Critical system PriorityClass
   - Run these ONLY on explicit user request
   - Do NOT treat WARNING from optional check as upgrade blocker
   - Do NOT make user decision to skip optional checks

6. **DETERMINISTIC GITREPO REMEDIATION PATTERN**
   - Strict pattern for deprecated gitRepo volume replacement
   - Replace gitRepo with git-sync init container
   - Mount git-sync-data at /git with git-sync init container
   - Mount git-source at application container's existing path
   - Use exact parameters (git-sync:v4.7.1, args, mounts)
   - Only use after this pattern actually fails, then try alternative

7. **PDB REMEDIATION** — Scale or relax disruption budget
   - Identify affected PDB and workload
   - Make smallest safe change (scale replicas or adjust budget)
   - Verify result
   - Re-run upgrade-readiness assessment

8. **VERIFICATION** — Verify every write
   - Never claim success based solely on write call return
   - Verify actual result using read tools
   - Confirm version reached, provisioning state, pod health, etc.
   - Re-run readiness assessment after remediation

9. **FAILURE HANDLING** — Report exact error, no speculative retries
   - Report exact observed error
   - Do not perform speculative iterative writes
   - Do not silently switch remediation strategies
   - Stop and report failure unless current user explicitly authorizes alternative

#### 3. Credentials and Authentication

**Type**: Managed Identity (no shared secrets)

**Initialization**:
```python
credential = DefaultAzureCredential()
# Prefers user-assigned identity if AZURE_CLIENT_ID is set
# Falls back to system-assigned or user login
```

**Scopes**:
- Azure management APIs (AKS, storage, etc.)
- Foundry APIs (project access)
- OpenAI endpoints

**RBAC Roles Required**:
- Subscription or Resource Group: Contributor (for Foundry project)
- Target AKS Cluster: AKS Cluster User Role (for kubectl access)

#### 4. Tool Invocation (MCP Integration)

**Tool Discovery**:
```python
toolbox = FoundryToolbox(
    credential,
    url=TOOLBOX_ENDPOINT  # e.g., https://cog-*.services.ai.azure.com/api/projects/.../toolboxes/aks-agent-tools-v2/versions/1/mcp?api-version=v1
)

# Agent discovers tools via MCP Streamable HTTP
# FoundryToolbox wraps MCPStreamableHTTPTool with:
#   - Per-request credential attachment
#   - Call-ID forwarding for tracing
#   - Error handling and retry logic
```

**Tool Invocation**:
1. LLM generates tool call (tool name + parameters)
2. Agent Framework routes to toolbox
3. Toolbox marshals MCP call over Streamable HTTP
4. MCP server receives request, executes tool
5. Result returned as JSON
6. Agent processes result, determines next step

**Tool Categories** (29 tools total):

| Category | Count | Examples |
|----------|-------|----------|
| Discovery | 3 | aks_get_cluster_details, aks_get_node_pools, aks_get_available_upgrades |
| Validation | 9 | aks_check_node_health, aks_check_pod_health, aks_check_pdb, aks_check_storage, aks_check_deprecated_apis, aks_validate_upgrade_readiness, aks_plan_upgrade_preparation, aks_check_single_replica_services, aks_check_operator_health, aks_check_node_pool_surge, aks_check_priority_class |
| Upgrade Execution | 3 | aks_execute_confirmed_upgrade, aks_get_upgrade_execution_status, aks_upgrade_node_pool |
| Remediation | 9 | aks_remediate_pdb, aks_rollback_pdb_remediation, aks_remediate_pods, aks_remediate_node, aks_remediate_storage, aks_remediate_deprecated_apis, aks_generate_deprecated_api_manifests, aks_resolve_upgrade_issue |
| CLI Operations | 4 | aks_kubectl_read, aks_kubectl_write, aks_az_read, aks_az_write |

### Agent Reasoning Loop

```
Initialize
├─ Load instructions
├─ Connect to LLM
├─ Discover tools (MCP)
└─ Set up logging/tracing

User Request
├─ Parse message
└─ Append to conversation history

LLM Reasoning (Per Turn)
├─ System prompt + history + current message
├─ LLM generates response
│  ├─ If no tool call
│  │  └─ Return response to user
│  └─ If tool call
│     ├─ Parse tool name + parameters
│     ├─ Validate parameters
│     └─ Execute tool via MCP
│
├─ Tool Execution
│  ├─ Call MCP endpoint
│  ├─ Receive JSON result
│  └─ Parse result
│
├─ Loop Iteration
│  ├─ Append tool result to history
│  └─ Ask LLM: "What should we do next?"
│
└─ Exit Conditions
   ├─ LLM returns response (no tool call)
   ├─ Max iterations exceeded (safety limit)
   ├─ Error in tool execution (report error)
   └─ User interruption (cancel agent)
```

### Agent Context Window Management

**Model**: gpt-5-mini (8,192 tokens default, can handle up to 128K)

**Token Budget**:
```
System prompt          ~2,000 tokens  (instructions)
Conversation history   ~3,000 tokens  (depends on turn count)
Tool results          ~2,000 tokens  (cluster state snapshots)
Remaining            ~1,000 tokens  (response generation buffer)
```

**Memory**: 
- **Conversation History** — Maintained in agent session (not persistent)
- **Cluster State Snapshots** — Retrieved fresh on each tool call (no stale caching)
- **Tool Invocation Log** — Available to agent for context (included in response)

### Agent Output and Logging

**Response Channel**:
- Foundry Chat Response (browser/Teams)
- Plain text + markdown formatting
- Tool invocation trace (optional verbosity)

**Logging**:
- Application Insights (via Foundry diagnostics)
- Log Analytics (via linked workspace)
- Queryable via KQL (Kusto Query Language)
- Retention: 30 days (configurable)

**Logged Events**:
- Agent invocation (timestamp, user, subscription)
- Tool calls (tool name, parameters, duration)
- Tool results (truncated JSON, status codes)
- Errors (exceptions, timeouts, auth failures)
- Agent response completion

### Agent Scaling

**Throughput**: Foundry handles scaling automatically

**Concurrency**: 
- Multiple users/invocations in parallel
- Per-invocation isolation (separate agent instances)
- No shared state between invocations

**Limits**:
- Max execution time per invocation: 5-10 minutes (Foundry timeout)
- Max tool call timeout: 30 seconds per MCP call
- Max context window: 128K tokens (gpt-5-mini)

**Monitoring**:
- Invocation rate (requests/minute)
- Average response time (milliseconds)
- Error rate (% failures)
- LLM token consumption (cost tracking)

### Agent Deployment

**Prerequisites**:
- Foundry AI Project created (via `azd provision`)
- gpt-5-mini model deployed
- MCP server deployed and endpoint available (TOOLBOX_ENDPOINT)

**Deployment Steps**:
1. `git clone` repository
2. `azd provision` — Create Foundry project, model deployments, infrastructure
3. `azd deploy` — Build agent image, push to ACR, deploy to Foundry Agent Service
4. `azd ai agent invoke --local "message"` — Test locally
5. `azd ai agent invoke "message"` — Test deployed agent

**Agent Versioning**:
- Agent deployments are versioned (v1, v2, v3, ...)
- Previous versions remain available
- Agent endpoint specifies version (e.g., `/agents/agent-framework-agent-with-foundry-toolbox-responses/versions/14`)
- Rollback by invoking earlier version

### Agent Monitoring and Observability

**Metrics**:
```
/metrics
├─ Invocations (count, duration)
├─ Tool calls (by tool, success/failure)
├─ LLM tokens (input, output, cost)
├─ Errors (by type, rate)
└─ Availability (uptime %)
```

**Health Checks**:
- Agent liveness (responds to GET /)
- Foundry connectivity (can connect to project endpoint)
- LLM availability (can call gpt-5-mini)
- MCP connectivity (can reach toolbox/MCP endpoint)

**Debugging**:
- Enable verbose logging (env var: `DEBUG=true`)
- View tool invocation traces (include in response)
- Query Application Insights / Log Analytics

### Agent Limitations and Constraints

**Known Limitations**:
1. **Context Window** — Large cluster states may exceed token limit (mitigated by compact JSON schemas)
2. **Tool Timeouts** — Long-running operations (upgrade 10+ minutes) return in_progress status, require polling
3. **State Retention** — No persistent memory between invocations (stateless)
4. **Concurrency** — Write operations are sequential (in-process lock in MCP server prevents duplicates, but not cross-replica)
5. **Network Latency** — Agent → Toolbox → MCP → Azure APIs creates ~500ms-1s latency per tool call
6. **Approvals** — Explicit approval is instruction-based, not cryptographically signed (trust boundary is agent instructions)

**Mitigations**:
- Use compact jsonpath queries (instead of full JSON objects) for pod health
- Poll status instead of waiting for completion
- Clear instructions on approval requirements
- In-process lock for upgrades + idempotent Azure operations
- Use latest model version (gpt-5-mini) for reasoning quality

---

**Next**: [06-data-flow.md](06-data-flow.md) for detailed data flow  
**Status**: Production POC  
**Last Updated**: 2026-09-10

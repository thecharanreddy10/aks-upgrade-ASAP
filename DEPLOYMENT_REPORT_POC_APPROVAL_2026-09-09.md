# AKS Upgrade Approval POC — Deployment Report

**Date:** 2026-09-09  
**Deployment Status:** ✅ SUCCESS  
**Agent Version:** v13  
**MCP Status:** Active with write gate enabled

---

## PART 1 — MCP Write Gate Enable ✅

### Environment Variable Updated
- **Resource:** `aks-mcp` Container App (resource group `rg-aks_upgrd_agent`)
- **Change:** `AKS_UPGRADE_ENABLE_WRITE=true`
- **Revision:** aks-mcp--0000029 (active)
- **Verification:** `az containerapp show` confirmed value set to "true"
- **Scope:** MCP server only; no source code change

### MCP Safety Controls Remain Active
All existing safety controls continue to enforce authorization:
- `check_mode="full"` validation required
- Target-version authoritative checks
- Readiness validation mandatory
- Execution scope enforcement (control_plane_only prevention)
- Node pool SUPPORTED evidence requirement

---

## PART 2 — Agent Approval Policy Update ✅

### Policy: AKS UPGRADE HUMAN APPROVAL POLICY

The agent instructions have been replaced with a comprehensive human-approval policy that mandates explicit user confirmation before any AKS upgrade execution.

#### Key Principles

1. **Explicit Approval Required**
   - Never execute an AKS control-plane or node-pool upgrade without explicit user approval of the current plan
   - The approval must clearly refer to the specific upgrade being proposed
   - Examples of valid approval:
     - "Yes, proceed with the upgrade to 1.35.1."
     - "I approve the control-plane upgrade to 1.35.1."
     - "Yes, proceed with the complete cluster upgrade to 1.35.1."

2. **What Does NOT Count as Approval**
   - ❌ `AKS_UPGRADE_ENABLE_WRITE=true` 
   - ❌ The write tool being available
   - ❌ A successful readiness assessment
   - ❌ A previous approval
   - ❌ An approval from an earlier conversation or turn
   - ❌ A previously generated upgrade plan
   - ❌ The user asking only for assessment or recommendations
   - ❌ Ambiguous statements such as "okay", "looks good", "fine", or "go ahead"

3. **Mandatory Assessment → Plan → Stop → Ask → Execute Flow**
   ```
   USER: "Upgrade my AKS cluster to 1.35.1."
   
   AGENT:
   1. Gather cluster state
   2. Check upgrade availability
   3. Run readiness checks
   4. Determine supported path
   5. Present plan
   
   STOP AND ASK FOR APPROVAL
   
   USER: "Yes, I approve the control-plane upgrade to 1.35.1."
   
   AGENT:
   1. Call aks_execute_confirmed_upgrade
   2. Wait for completion
   3. Verify actual versions/state
   4. Report result
   ```

4. **Execution Scope Policy**
   - `control_plane_only` → Upgrade control plane only; no node-pool expansion
   - `complete_cluster` → Upgrade control plane + node pools (SUPPORTED evidence only)
   - Never convert control_plane_only approval to complete_cluster execution
   - Never infer node-pool approval from control-plane approval

5. **Separate Remediation from Upgrade Approval**
   - Remediating a Kubernetes blocker (e.g., "Fix the PDB issue") authorizes that remediation only
   - It does NOT authorize an AKS version upgrade
   - An AKS upgrade always requires separate explicit approval

6. **Assessment Mode**
   - Use read-only tools only
   - Do not modify AKS resources
   - Do not execute an upgrade
   - Report blockers, warnings, and recommendations
   - Stop after assessment and offer upgrade plan for explicit approval

7. **Post-Upgrade Verification**
   - Always verify actual control-plane version and provisioning state
   - Always verify node-pool versions where applicable
   - Never claim success based solely on write call return status
   - Report whether the requested scope was actually completed

---

## PART 3 — Deployment & Verification ✅

### Agent Deployment
- **Tool:** azd deploy (Microsoft Foundry)
- **Duration:** 4 seconds
- **Result:** SUCCESS
- **Deployed Agent Version:** agent-framework-agent-with-foundry-toolbox-responses:v13
- **Status:** Active

### Endpoint Information
- **Agent Endpoint (Responses Protocol):** 
  ```
  https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found/agents/agent-framework-agent-with-foundry-toolbox-responses/endpoint/protocols/openai/responses?api-version=v1
  ```
- **Playground URL:** 
  ```
  https://ai.azure.com/nextgen/r/uw4sntf7ReSSz2VPOA5jiA,rg-agent-framework-agent-with-foundry-toolbox-responses-dev-526c3b27,,cog-vtjc46vefyyj6,agent-framework-agent-with-found/build/agents/agent-framework-agent-with-foundry-toolbox-responses/build?version=13
  ```

### MCP Toolbox Connection
- **Toolbox:** aks-agent-tools-v2:v1
- **MCP Server Label:** aks-ops
- **MCP Server URL:** https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp
- **Foundry Approval Gate:** require_approval: "never" (no Foundry-level approval UI)
- **Connection Status:** Active and verified

### Test Validation
- **Full MCP Test Suite:** 177/177 PASS
- **Agent Instruction Tests:** All assertions updated and passing
- **Test Coverage:**
  - Authorization contract enforcement
  - Scope validation
  - Readiness checks
  - Post-upgrade verification
  - Agent instruction policy compliance

---

## Expected Conversation Flow

### Scenario 1: User Requests Assessment Only
```
USER:
"Check if my cluster can upgrade to 1.35.1"

AGENT:
1. Runs aks_get_upgrade_readiness_status (read-only)
2. Gathers cluster state (read-only)
3. Presents findings:
   - Current control plane: 1.35.0
   - Target: 1.35.1
   - Control plane: SUPPORTED
   - Node pool nodepool1: INSUFFICIENT_EVIDENCE
   - Mandatory readiness: PASS
   - Proposed scope: control_plane_only

STOPS HERE — Does not propose execution
```

### Scenario 2: User Requests Assessment + Asks for Recommendation
```
USER:
"Should I upgrade my cluster to 1.35.1?"

AGENT:
1. Runs assessment (same as Scenario 1)
2. Offers recommendation:
   "Based on readiness checks, a control_plane_only upgrade to 1.35.1 is supported.
    Node pool nodepool1 lacks sufficient evidence for upgrade.
    If you want to proceed, I'll need your explicit approval of the control-plane upgrade."

STOPS HERE — Waits for explicit user approval
Does NOT automatically execute even though assessment passed
```

### Scenario 3: User Approves Execution
```
USER (after assessment):
"Yes, I approve the control-plane upgrade to 1.35.1."

AGENT:
1. Recognizes approval matches current plan
2. Calls aks_execute_confirmed_upgrade(
     is_user_confirmed=true,
     confirmed_scope="control_plane_only",
     target_version="1.35.1"
   )
3. Waits for execution completion
4. Re-reads cluster state (verification)
5. Reports actual result:
   "Control plane upgrade completed.
    Control plane version: 1.35.1 ✓
    Node pool nodepool1 version: 1.35.0 (no change per plan)
    Provisioning state: Succeeded"
```

### Scenario 4: User Provides Ambiguous Statement
```
USER (after assessment):
"Looks good, let's do it."

AGENT:
REJECTS EXECUTION
"I need explicit confirmation that you approve the control-plane upgrade to 1.35.1. 
Please confirm with: 'I approve the control-plane upgrade to 1.35.1' or similar."

WAITS FOR CLEAR APPROVAL
```

### Scenario 5: Remediation, Then Upgrade
```
USER:
"Fix the PDB issue and upgrade the cluster."

AGENT:
1. Interprets as two separate operations
2. Runs readiness check (sees PDB blocker)
3. Offers PDB remediation with explicit wording:
   "The PDB issue is blocking the upgrade. I can fix it now."

USER:
"Yes, fix it."

AGENT:
1. Applies PDB remediation (authorized by current request)
2. Re-runs readiness check
3. Presents upgrade plan:
   "Readiness now passes. Control plane can upgrade to 1.35.1.
    Do you explicitly approve this upgrade?"

WAITS FOR SEPARATE EXPLICIT UPGRADE APPROVAL
Remediation approval does NOT authorize the upgrade
```

---

## Current Cluster State
- **Control Plane Version:** 1.35.1 (from previous live test)
- **Node Pool (nodepool1) Version:** 1.35.0
- **Provisioning State:** Succeeded
- **Note:** No additional AKS writes performed during this task

---

## Security Properties

### What This Design Achieves
1. ✅ **Explicit User Approval Required** — No automatic execution even with assessment passing
2. ✅ **Write Gate Enabled at Deployment Level** — Operator has explicitly enabled write capability
3. ✅ **MCP Readiness/Scope Checks Enforce** — All existing safety controls remain active
4. ✅ **Clear Conversation Boundaries** — Assessment, plan, approval, execution are distinct steps
5. ✅ **No Ambiguity** — Specific approval examples provided; generic statements rejected

### Important Architectural Note
The `is_user_confirmed=true` parameter in the MCP tool call remains a **contractual signal** to the MCP server, not a cryptographically trusted proof of human approval. The **true security boundary** is:
- **Operator-controlled deployment environment variable** (`AKS_UPGRADE_ENABLE_WRITE=true`)
- **Agent conversation flow** enforcing explicit user approval in the current conversation
- **MCP server safety controls** enforcing readiness/scope/target validation

The agent instructions ensure that `is_user_confirmed=true` is only set after explicit user confirmation in the conversation thread, but this design assumes the agent honors the instruction contract.

---

## Files Modified

1. **[src/agent-framework-agent-with-foundry-toolbox-responses/main.py](../src/agent-framework-agent-with-foundry-toolbox-responses/main.py)**
   - Replaced "EXPLICIT CONFIRMATION CONTRACT" with "AKS UPGRADE HUMAN APPROVAL POLICY"
   - Added comprehensive approval flow requirements
   - Added execution scope policy
   - Added separate remediation/upgrade authorization
   - All 13 major policy sections updated

2. **[src/aks-operations-mcp/tests/test_upgrade_execution.py](../src/aks-operations-mcp/tests/test_upgrade_execution.py)**
   - Updated 4 agent instruction assertion tests to verify new policy
   - Added regression test documenting authorization flaw discovered in live testing
   - All 177 tests passing

---

## Deployment Checklist

- ✅ `AKS_UPGRADE_ENABLE_WRITE=true` set on MCP Container App
- ✅ Agent instructions updated with comprehensive approval policy
- ✅ Agent deployed to Foundry (v13, active)
- ✅ MCP toolbox connection verified
- ✅ All tests passing (177/177)
- ✅ No AKS cluster writes performed during this task
- ✅ Write gate enforcement remains operational
- ✅ Readiness/scope/target validation remains operational
- ✅ Post-upgrade verification checks enabled
- ✅ Separate remediation/upgrade authorization enforced

---

## Next Steps for Validation

To test the approval flow:

1. **Via Foundry Agent Playground:**
   - Visit the playground URL above
   - Start a new conversation
   - Ask: "Check if my cluster can upgrade to 1.35.1"
   - Verify agent stops after assessment and asks for approval
   - Respond: "Yes, I approve the control-plane upgrade to 1.35.1."
   - Verify agent executes upgrade only after explicit approval

2. **Via API:**
   ```bash
   curl -X POST https://cog-vtjc46vefyyj6.services.ai.azure.com/api/projects/agent-framework-agent-with-found/agents/agent-framework-agent-with-foundry-toolbox-responses/endpoint/protocols/openai/responses?api-version=v1 \
     -H "Content-Type: application/json" \
     -d '{"messages": [{"role": "user", "content": "Check if cluster can upgrade to 1.35.1"}]}'
   ```

---

**Status:** Deployment complete and ready for validation testing.

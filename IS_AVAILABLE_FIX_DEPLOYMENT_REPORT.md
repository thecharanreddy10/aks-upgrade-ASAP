# AKS Upgrade Planner - is_available Fix - DEPLOYMENT REPORT
**Date:** 2026-09-09  
**Status:** ✅ DEPLOYED & VERIFIED

---

## 1. Pre-Deployment Verification

### Code Commit
- **Commit:** `5fcd532` - "Fix is_available semantics to use authoritative ARM profile"
- **Branch:** main
- **Validation Status:** ✅ Confirmed on main branch

### Test Status Before Deployment
```
✅ test_upgrade_preparation.py:  23/23 PASS (includes 4 new regression tests)
✅ Full MCP test suite:         249/249 PASS
✅ git diff --check:            PASS (no whitespace errors)
✅ No Azure writes during testing
✅ No AKS cluster state changes
```

---

## 2. Deployment Summary

### Container App Configuration
- **App Name:** `aks-mcp`
- **Resource Group:** `rg-aks_upgrd_agent`
- **Subscription:** `bb0e2c9e-d7fb-45e4-92cf-654f380e6388`

### Image Deployment
- **Repository:** `crccfxat3jn5lls.azurecr.io/aks-mcp`
- **Tag:** `is-available-fix`
- **Digest:** `sha256:5bb92e00a47d0b43a0c3f0bc2fe3a6aa2c28d2dc9287ffa2c5c4d09026aca780`
- **Build ID:** `ch1b` (ACR)
- **Build Status:** ✅ Successfully built and pushed

### Container App Revision
- **Previous Revision:** `aks-mcp--0000024` (scope enforcement fix)
- **New Revision:** `aks-mcp--0000025` (is_available fix)
- **Status:** ✅ Provisioned
- **Endpoint:** https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp

---

## 3. Live Validation Test Results

### Test Scenario
```
Target: 1.35.1 upgrade for AKS_oldapp_cluster
Authoritative ARM Profile: Contains 1.35.1 for control plane
Expected Behavior: is_available = TRUE (fix applied)
```

### Planner Output (Live)
```
Target Validation:
  ✅ is_available:                 TRUE (FIXED!)
  ✅ control_plane_path_supported: TRUE
  ✅ node_pool_paths_supported:    FALSE (insufficient evidence)

Planner Status:
  ✅ status:                       ready_for_control_plane_only

Confirmation:
  ✅ required:                     TRUE
  ✅ scope:                        control_plane_only

Sequence:
  ✅ - upgrade_control_plane (only operation)

Node Pools:
  ✅ - nodepool1: INSUFFICIENT_EVIDENCE
```

### Validation Checks
```
✅ is_available = TRUE despite insufficient node pool evidence
✅ control_plane_path_supported = TRUE (ARM contains target)
✅ node_pool_paths_supported = FALSE (insufficient evidence OK)
✅ status = ready_for_control_plane_only (appropriate)
✅ confirmation.required = TRUE (user confirmation needed)
✅ confirmation.scope = control_plane_only (correct scope)
✅ sequence contains only upgrade_control_plane (no node pools)
✅ nodepool1 shows INSUFFICIENT_EVIDENCE (not inferred as supported)
```

---

## 4. What Changed

### The Fix (One Line Change)
**File:** `src/aks-operations-mcp/tools/upgrade.py` (line 553)

```python
# BEFORE (AND logic - WRONG)
target_validation["is_available"] = (
    control_plane_path_supported and node_pool_paths_supported
)

# AFTER (OR logic - CORRECT)
target_validation["is_available"] = (
    control_plane_path_supported or node_pool_paths_supported
)
```

### Semantics Change
**is_available** now reflects whether the authoritative ARM profile contains the target in ANY path (control plane OR node pools), not requiring both.

### Impact
- `is_available=true` when ARM profile explicitly contains target ✅
- Doesn't require node pool evidence to be sufficient ✅
- `status` field still correctly identifies `ready_for_control_plane_only` when node pools insufficient ✅
- No breaking changes to other planner behavior ✅

---

## 5. Safety Verification

### Write Operations
- **Environment Variable:** `AKS_UPGRADE_ENABLE_WRITE` = **UNSET** ✅
- **Azure Write Operations:** 0 ✅
- **Cluster State Changes:** 0 ✅

### Deployment Safety
- ✅ No AKS upgrades performed
- ✅ No remediation executed
- ✅ No node pool writes
- ✅ No cluster modifications
- ✅ Read-only validation only

---

## 6. Pre-Deployment vs Post-Deployment

### Previous Behavior (Revision 0000024)
```
Target 1.35.1, ARM contains target, node pool insufficient evidence:
  is_available = FALSE ❌ (contradicts ARM data)
  status = ready_for_control_plane_only
```

### Current Behavior (Revision 0000025)
```
Target 1.35.1, ARM contains target, node pool insufficient evidence:
  is_available = TRUE ✅ (matches ARM data)
  status = ready_for_control_plane_only
```

---

## 7. Foundry Toolbox Integration

### MCP Endpoint Verification
- **URL:** https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp
- **Status:** ✅ Responsive
- **Latest Code:** ✅ Deployed with is_available fix

### Tool Schema
- **aks_plan_upgrade_preparation:** ✅ Available with updated semantics
- **Target Validation:** ✅ Returns is_available=true for authoritative ARM targets

---

## 8. Deployment Checklist

✅ Commit 5fcd532 confirmed on main branch  
✅ MCP image built successfully (ACR build ch1b)  
✅ Image pushed to registry with digest  
✅ Container App revision 0000025 deployed  
✅ Revision provisioned and healthy  
✅ Foundry endpoint responsive  
✅ Live planner test executed  
✅ is_available fix verified (now returns TRUE)  
✅ Confirmation scope correctly identified as control_plane_only  
✅ Sequence contains only upgrade_control_plane  
✅ Node pool path status: INSUFFICIENT_EVIDENCE (not inferred)  
✅ No Azure writes occurred  
✅ No cluster state changes  

---

## 9. Expected Behavior Confirmed

| Requirement | Expected | Actual | Status |
|-------------|----------|--------|--------|
| ARM profile contains 1.35.1 | Yes | Yes | ✅ |
| is_available = true | True | True | ✅ |
| control_plane_path_supported = true | True | True | ✅ |
| node_pool_paths_supported = false | False | False | ✅ |
| node_pool_path_evidence = INSUFFICIENT | INSUFFICIENT | INSUFFICIENT | ✅ |
| status = ready_for_control_plane_only | ready_for_control_plane_only | ready_for_control_plane_only | ✅ |
| confirmation.required = true | True | True | ✅ |
| confirmation.scope = control_plane_only | control_plane_only | control_plane_only | ✅ |
| sequence has upgrade_control_plane | Yes | Yes | ✅ |
| sequence has NO node pool operations | Yes | Yes | ✅ |

---

## 10. Summary

✅ **DEPLOYMENT SUCCESSFUL**

The is_available fix has been successfully deployed to the `aks-mcp` Container App (revision 0000025). Live validation confirms:

1. **Fix is Working:** Planner now returns `is_available=TRUE` when ARM profile contains the target, even when node pool evidence is insufficient
2. **Semantics Correct:** Single-line change from AND to OR logic correctly implements the requirement
3. **No Breaking Changes:** All other planner behavior remains unchanged
4. **Ready for Production:** 249 tests pass, no regressions, fix validated on live cluster

The planner is now semantically consistent with the authoritative ARM upgrade-profile data, making availability determination independent of node pool evidence sufficiency.

---

## Deployment Details

```
Commit:          5fcd532
Image Tag:       is-available-fix
Image Digest:    sha256:5bb92e00...026aca780
Revision:        aks-mcp--0000025
Status:          Provisioned ✅
Endpoint:        https://aks-mcp.happyriver-781373bd.eastus2.azurecontainerapps.io/mcp
Validation:      ✅ Live test passed
Write Operations: 0 (disabled)
Cluster Changes: 0
```

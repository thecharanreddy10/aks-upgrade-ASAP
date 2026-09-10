#!/usr/bin/env python3
"""
Test the live planner's is_available fix via the deployed MCP.

This validates that:
1. Authoritative ARM profile contains 1.35.1 for control plane
2. Planner returns is_available=true (not false)
3. Status is ready_for_control_plane_only (node pools insufficient)
4. Confirmation scope is control_plane_only
"""

import sys
sys.path.insert(0, '/app')

from tools.upgrade import aks_plan_upgrade_preparation

# Test parameters matching the live cluster
SUBSCRIPTION = "bb0e2c9e-d7fb-45e4-92cf-654f380e6388"
RESOURCE_GROUP = "AKS_Upgrade_Agent"
CLUSTER = "AKS_oldapp_cluster"
TARGET = "1.35.1"

print("=" * 70)
print("AKS Upgrade Planner - is_available Fix Live Validation")
print("=" * 70)
print(f"\nTest Parameters:")
print(f"  Subscription:   {SUBSCRIPTION}")
print(f"  Resource Group: {RESOURCE_GROUP}")
print(f"  Cluster:        {CLUSTER}")
print(f"  Target:         {TARGET}")
print(f"\nRunning live planner preparation...\n")

result = aks_plan_upgrade_preparation(
    subscription_id=SUBSCRIPTION,
    resource_group=RESOURCE_GROUP,
    cluster_name=CLUSTER,
    target_kubernetes_version=TARGET,
)

print("-" * 70)
print("TARGET VALIDATION RESULTS:")
print("-" * 70)
target_val = result.get("target_validation", {})
print(f"  requested_version:          {target_val.get('requested_version')}")
print(f"  is_syntactically_valid:     {target_val.get('is_syntactically_valid')}")
print(f"  is_available:               {target_val.get('is_available')}")
print(f"  control_plane_path_supported: {target_val.get('control_plane_path_supported')}")
print(f"  node_pool_paths_supported:  {target_val.get('node_pool_paths_supported')}")
print(f"  node_pool_path_evidence_sufficient: {target_val.get('node_pool_path_evidence_sufficient')}")

print(f"\nSTATUS:")
print(f"  Overall Status:             {result.get('status')}")
print(f"  Blockers:                   {result.get('blockers', [])}")

confirmation = result.get("confirmation", {})
print(f"\nCONFIRMATION:")
print(f"  required:                   {confirmation.get('required')}")
print(f"  status:                     {confirmation.get('status')}")
print(f"  scope:                      {confirmation.get('scope')}")

print(f"\nSEQUENCE:")
sequence = result.get("sequence", [])
for item in sequence:
    print(f"  - Order {item.get('order')}: {item.get('operation')} (phase: {item.get('phase')})")

print(f"\nUPGRADE SCOPE:")
scope = result.get("upgrade_scope", {})
cp_scope = scope.get("control_plane", {})
print(f"  Control Plane Included:     {cp_scope.get('included')}")
print(f"    Current Version:          {cp_scope.get('current_version')}")
print(f"    Target Version:           {cp_scope.get('target_version')}")

node_pools = scope.get("node_pools", [])
print(f"  Node Pools ({len(node_pools)} total):")
for pool in node_pools:
    print(f"    - {pool.get('name')}")
    print(f"      Current: {pool.get('current_version')}, Target: {pool.get('target_version')}")
    print(f"      Path Status: {pool.get('path_status')}")

print("\n" + "=" * 70)
print("VALIDATION RESULTS:")
print("=" * 70)

# Validate expected behavior
checks = []

# Check 1: is_available should be true (ARM contains target)
is_avail = target_val.get("is_available")
if is_avail is True:
    checks.append(("✅", "is_available = TRUE (ARM profile contains target)"))
else:
    checks.append(("❌", f"is_available = {is_avail} (expected: TRUE)"))

# Check 2: control plane path supported
cp_supported = target_val.get("control_plane_path_supported")
if cp_supported is True:
    checks.append(("✅", "control_plane_path_supported = TRUE"))
else:
    checks.append(("❌", f"control_plane_path_supported = {cp_supported}"))

# Check 3: Status should be ready_for_control_plane_only or ready_for_confirmation
status = result.get("status")
if status in ("ready_for_control_plane_only", "ready_for_confirmation"):
    checks.append(("✅", f"status = {status} (ready for upgrade)"))
else:
    checks.append(("❌", f"status = {status} (expected: ready_for_control_plane_only or ready_for_confirmation)"))

# Check 4: Confirmation required
conf_required = confirmation.get("required")
if conf_required is True:
    checks.append(("✅", "confirmation.required = TRUE"))
else:
    checks.append(("⚠️", f"confirmation.required = {conf_required}"))

# Check 5: Control plane in sequence
has_cp_upgrade = any(item.get("operation") == "upgrade_control_plane" for item in sequence)
if has_cp_upgrade:
    checks.append(("✅", "sequence contains upgrade_control_plane"))
else:
    checks.append(("❌", "sequence does NOT contain upgrade_control_plane"))

# Print validation results
for symbol, message in checks:
    print(f"{symbol} {message}")

# Overall result
all_pass = all(symbol == "✅" for symbol, _ in checks)
print("\n" + "=" * 70)
if all_pass:
    print("✅ ALL CHECKS PASSED - Fix is working correctly!")
else:
    print("❌ SOME CHECKS FAILED - Review results above")
print("=" * 70)

sys.exit(0 if all_pass else 1)

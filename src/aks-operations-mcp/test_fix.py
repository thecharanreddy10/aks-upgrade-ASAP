#!/usr/bin/env python3
"""Test planner is_available fix with live cluster."""

import sys
sys.path.insert(0, '.')

from tools.upgrade import aks_plan_upgrade_preparation

SUBSCRIPTION = "bb0e2c9e-d7fb-45e4-92cf-654f380e6388"
RESOURCE_GROUP = "AKS_Upgrade_Agent"
CLUSTER = "AKS_oldapp_cluster"
TARGET = "1.35.1"

print("=" * 70)
print("Testing planner is_available fix with live cluster (1.35.1)")
print("=" * 70)

result = aks_plan_upgrade_preparation(
    subscription_id=SUBSCRIPTION,
    resource_group=RESOURCE_GROUP,
    cluster_name=CLUSTER,
    target_kubernetes_version=TARGET,
)

target_val = result.get("target_validation", {})
conf = result.get("confirmation", {})
scope = result.get("upgrade_scope", {})

print(f"\nTarget Validation:")
print(f"  is_available:                 {target_val.get('is_available')}")
print(f"  control_plane_path_supported: {target_val.get('control_plane_path_supported')}")
print(f"  node_pool_paths_supported:    {target_val.get('node_pool_paths_supported')}")

print(f"\nPlanner Status:")
print(f"  status:                       {result.get('status')}")

print(f"\nConfirmation:")
print(f"  required:                     {conf.get('required')}")
print(f"  scope:                        {conf.get('scope')}")

print(f"\nSequence:")
for item in result.get("sequence", []):
    print(f"  - {item.get('operation')}")

print(f"\nNode Pools:")
for pool in scope.get("node_pools", []):
    print(f"  - {pool.get('name')}: {pool.get('path_status')}")

print("\n" + "=" * 70)
# Validation
is_avail = target_val.get("is_available")
cp_supported = target_val.get("control_plane_path_supported")
status = result.get("status")

if is_avail is True and cp_supported is True and status in ("ready_for_control_plane_only", "ready_for_confirmation"):
    print("✅ FIX VERIFIED: is_available=TRUE despite insufficient node pool evidence")
else:
    print(f"❌ ISSUE: is_available={is_avail}, cp_supported={cp_supported}, status={status}")
print("=" * 70)

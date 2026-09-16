"""Lightweight upgrade-issue orchestration helpers for the MCP agent.

The resolver deliberately delegates execution to existing MCP remediation tools and
new controlled CLI tools. It never accepts or requires an application approval token.
"""

from __future__ import annotations

from typing import Any

from tools.cli_operations import aks_az_read, aks_az_write, aks_kubectl_read, aks_kubectl_write
from tools.deprecated_apis import aks_check_deprecated_apis
from tools.remediate_deprecated_apis import aks_remediate_deprecated_apis
from tools.remediate_nodes import aks_remediate_node
from tools.remediate_pdb import aks_remediate_pdb
from tools.remediate_pods import aks_remediate_pods
from tools.remediate_storage import aks_remediate_storage


_REMEDIATION_CAPABILITIES: dict[str, dict[str, Any]] = {
    "pdb": {
        "status": "AUTOMATABLE",
        "tools": ["aks_remediate_pdb"],
        "strategies": ["scale_workload_up", "relax_pdb"],
        "operator_steps": ["Identify the blocking PDB and protected workload before choosing the smallest change."],
    },
    "pods": {
        "status": "AUTOMATABLE",
        "tools": ["aks_remediate_pods"],
        "strategies": ["rollout_restart", "delete_pod"],
        "operator_steps": ["Inspect pod events and owner references before restarting or recreating a pod."],
    },
    "storage": {
        "status": "CONDITIONAL",
        "tools": ["aks_remediate_storage"],
        "strategies": ["cleanup_pvc", "cleanup_pv"],
        "operator_steps": [
            "Take or confirm a backup before changing persistent storage.",
            "For Multi-Attach or RWO/RWX design problems, change the workload/storage architecture rather than deleting a healthy PVC.",
        ],
    },
    "storage_migration": {
        "status": "OPERATOR_GUIDED",
        "tools": ["aks_check_storage", "aks_kubectl_read"],
        "strategies": [],
        "operator_steps": [
            "Map the workload, replicas, PVC access mode, StorageClass, and data ownership.",
            "Design and test the RWO-to-RWX or per-replica storage migration outside the agent.",
            "Do not delete a healthy PVC/PV or migrate application data automatically.",
        ],
    },
    "node": {
        "status": "AUTOMATABLE",
        "tools": ["aks_remediate_node"],
        "strategies": ["drain_node", "restart_node"],
        "operator_steps": ["Confirm workload redundancy and PDB impact before draining or restarting a node."],
    },
    "api": {
        "status": "CONDITIONAL",
        "tools": ["aks_remediate_deprecated_apis", "aks_generate_deprecated_api_manifests"],
        "strategies": ["generate_migration_guidance"],
        "operator_steps": [
            "Update the owning chart, controller, or source manifest to the supported API version.",
            "Run server-side dry-run and test schema changes before applying the migration.",
        ],
    },
    "webhook": {
        "status": "OPERATOR_GUIDED",
        "tools": ["aks_kubectl_read", "aks_kubectl_write"],
        "strategies": [],
        "operator_steps": [
            "Inspect webhook service endpoints, CA bundles, certificate expiry, and timeout events.",
            "Renew or repair the owning controller certificate; do not delete a webhook blindly.",
        ],
    },
    "addon": {
        "status": "OPERATOR_GUIDED",
        "tools": ["aks_kubectl_read", "aks_az_read", "aks_az_write"],
        "strategies": [],
        "operator_steps": [
            "Check AKS, CSI, CNI, kube-proxy, and ingress compatibility with the target Kubernetes version.",
            "Upgrade the vendor or AKS add-on only after confirming its supported version matrix.",
        ],
    },
    "crd": {
        "status": "OPERATOR_GUIDED",
        "tools": ["aks_kubectl_read", "aks_generate_deprecated_api_manifests"],
        "strategies": [],
        "operator_steps": [
            "Use aks_plan_crd_conversion for read-only analysis, then upgrade the CRD and operator together outside automated remediation.",
            "Test conversion of existing CRs and define rollback before any operator applies a migration.",
        ],
    },
    "backup": {
        "status": "OPERATOR_GUIDED",
        "tools": ["aks_az_read", "aks_kubectl_read"],
        "strategies": [],
        "operator_steps": [
            "Confirm recent application backups and PV snapshots before destructive remediation or another upgrade.",
        ],
    },
}


def aks_plan_upgrade_issue_remediation(
    category: str,
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    strategy: str | None = None,
    namespace: str | None = None,
    resource_name: str | None = None,
    target_version: str | None = None,
) -> dict[str, Any]:
    """Create a no-write remediation plan for a detected upgrade blocker."""
    normalized = category.strip().lower().replace("-", "_")
    aliases = {"pdb": "pdb", "pod": "pods", "node": "node", "storage": "storage", "storage_migration": "storage_migration", "rwo_rwx": "storage_migration", "api": "api", "deprecated_api": "api"}
    normalized = aliases.get(normalized, normalized)
    capability = _REMEDIATION_CAPABILITIES.get(normalized)
    if capability is None:
        raise ValueError(f"Unsupported remediation category: {category!r}")

    if capability["status"] == "OPERATOR_GUIDED":
        return {
            "status": "operator_guided",
            "category": normalized,
            "strategy": strategy,
            "message": "No dedicated safe remediation tool is available for this category.",
            "operator_steps": capability["operator_steps"],
            "required_authorization": "Authorize the exact change only after reviewing the proposed steps.",
            "writes_performed": False,
        }

    if normalized == "pdb":
        if not namespace or not resource_name:
            raise ValueError("PDB planning requires namespace and resource_name (PDB name).")
        result = aks_remediate_pdb(subscription_id, resource_group, cluster_name, namespace, resource_name, strategy or "scale_workload_up", dry_run=True)
    elif normalized == "pods":
        if not namespace or not resource_name:
            raise ValueError("Pod planning requires namespace and resource_name (pod name).")
        result = aks_remediate_pods(subscription_id, resource_group, cluster_name, namespace, resource_name, strategy or "rollout_restart", dry_run=True)
    elif normalized == "node":
        if not resource_name:
            raise ValueError("Node planning requires resource_name (node name).")
        result = aks_remediate_node(subscription_id, resource_group, cluster_name, resource_name, strategy or "drain_node", dry_run=True)
    elif normalized == "storage":
        result = aks_remediate_storage(subscription_id, resource_group, cluster_name, namespace, resource_name, strategy or "cleanup_pvc", dry_run=True)
    else:
        result = aks_remediate_deprecated_apis(subscription_id, resource_group, cluster_name, target_version or "1.35")

    return {
        "status": "dry_run",
        "category": normalized,
        "strategy": strategy,
        "writes_performed": False,
        "authorization_required_to_apply": True,
        "plan": result,
    }


def aks_resolve_upgrade_issue(
    issue: str,
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    target_version: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Investigate an upgrade issue and return a structured next-action plan.

    This planner is intentionally conservative: it recommends dedicated remediation tools
    for known blockers and generic CLI investigation for unforeseen workload/infrastructure
    failures. Actual generic writes remain behind full check mode and the existing write gate.
    """
    if not issue or not issue.strip():
        raise ValueError("issue must be a non-empty description")

    lowered = issue.lower()
    checks: list[dict[str, Any]] = []

    if any(term in lowered for term in ("pdb", "disruption", "eviction", "drain")):
        checks.append({"category": "pdb", "recommended_tool": "aks_check_pdb"})
    if any(term in lowered for term in ("pod", "pending", "crashloop", "unschedul", "container")):
        checks.append({"category": "pods", "recommended_tool": "aks_check_pod_health"})
    if any(term in lowered for term in ("pvc", "pv", "storage", "volume", "csi")):
        checks.append({"category": "storage", "recommended_tool": "aks_check_storage"})
    if any(term in lowered for term in ("multi-attach", "multi attach", "rwo", "rwx", "storage migration", "storageclass migration")):
        checks.append({"category": "storage_migration", "recommended_tool": "aks_check_storage"})
    if any(term in lowered for term in ("node", "cordon", "drain")):
        checks.append({"category": "node", "recommended_tool": "aks_check_node_health"})
    if any(term in lowered for term in ("deprecated", "removed api", "api version")):
        checks.append({"category": "api", "recommended_tool": "aks_check_deprecated_apis"})
    if "crd" in lowered or "custom resource definition" in lowered:
        checks.append({"category": "crd", "recommended_tool": "aks_kubectl_read"})
    if any(term in lowered for term in ("webhook", "admission", "certificate", "cabundle")):
        checks.append({"category": "webhook", "recommended_tool": "aks_kubectl_read"})
    if any(term in lowered for term in ("csi", "cni", "addon", "add-on", "ingress controller", "kube-proxy")):
        checks.append({"category": "addon", "recommended_tool": "aks_az_read"})
    if any(term in lowered for term in ("backup", "snapshot", "disaster recovery", "recovery")):
        checks.append({"category": "backup", "recommended_tool": "aks_az_read"})

    if not checks:
        checks = [
            {"category": "cluster", "recommended_tool": "aks_get_cluster_details"},
            {"category": "nodes", "recommended_tool": "aks_check_node_health"},
            {"category": "pods", "recommended_tool": "aks_check_pod_health"},
            {"category": "pdb", "recommended_tool": "aks_check_pdb"},
            {"category": "storage", "recommended_tool": "aks_check_storage"},
            {"category": "apis", "recommended_tool": "aks_check_deprecated_apis"},
        ]

    categories = [item["category"] for item in checks]
    remediation_capabilities = [
        {"category": category, **_REMEDIATION_CAPABILITIES[category]}
        for category in categories
        if category in _REMEDIATION_CAPABILITIES
    ]
    return {
        "issue": issue,
        "target_version": target_version,
        "dry_run": dry_run,
        "recommended_checks": checks,
        "remediation_capabilities": remediation_capabilities,
        "remediation_policy": {
            "automate": "Use a dedicated remediation tool when the current user explicitly authorizes the specific fix.",
            "conditional": "Run the dedicated tool only after its safety preconditions are satisfied; otherwise provide the listed operator steps.",
            "operator_guided": "Do not infer or execute a risky migration. Provide the listed steps and stop for explicit, specific authorization.",
        },
        "dynamic_cli_available": True,
        "cli_hint": "Use aks_kubectl_read/aks_az_read to investigate details not covered by dedicated tools, then use aks_kubectl_write/aks_az_write only when a concrete remediation is understood.",
        "write_policy": "Use dedicated remediation tools first; generic writes require full check_mode and AKS_REMEDIATION_ENABLE_WRITE=true.",
    }


__all__ = [
    "aks_az_read",
    "aks_az_write",
    "aks_kubectl_read",
    "aks_kubectl_write",
    "aks_resolve_upgrade_issue",
]

"""Read-only Helm/operator and platform add-on remediation planning."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, run_kubectl_raw, validate_k8s_name


def _items(batch: dict[str, tuple[int, str]], label: str) -> list[dict[str, Any]]:
    exit_code, raw = batch.get(label, (1, ""))
    if exit_code != 0 or not raw.strip():
        return []
    try:
        return json.loads(raw, strict=False).get("items", [])
    except json.JSONDecodeError:
        return []


def aks_plan_platform_addon_remediation(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    category: str,
    resource_name: str | None = None,
    target_version: str | None = None,
) -> dict[str, Any]:
    """Create a no-write remediation plan for an add-on, Helm release, or operator issue."""
    normalized = category.strip().lower().replace("-", "_")
    allowed = {"helm", "operator", "csi", "cni", "addon", "ingress"}
    if normalized not in allowed:
        raise ValueError(f"category must be one of {sorted(allowed)}")
    if resource_name:
        validate_k8s_name(resource_name, "platform resource")

    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "daemonsets": "get daemonset -A",
            "deployments": "get deployment -A",
            "csidrivers": "get csidrivers",
            "storageclasses": "get storageclass",
        },
    )
    daemonsets = _items(batch, "daemonsets")
    deployments = _items(batch, "deployments")
    csidrivers = _items(batch, "csidrivers")
    storageclasses = _items(batch, "storageclasses")

    helm_releases: list[dict[str, Any]] = []
    helm_error: str | None = None
    try:
        raw = run_kubectl_raw(subscription_id, resource_group, cluster_name, "helm ls -A -o json")
        parsed = json.loads(raw, strict=False)
        helm_releases = parsed if isinstance(parsed, list) else parsed.get("items", [])
    except Exception as exc:  # noqa: BLE001
        helm_error = str(exc)

    selected_helm = [
        release for release in helm_releases
        if not resource_name or release.get("name") == resource_name or release.get("chart", "").startswith(resource_name)
    ]
    selected_workloads = [
        item for item in daemonsets + deployments
        if not resource_name or item.get("metadata", {}).get("name") == resource_name
    ]

    if normalized in {"csi", "cni", "addon", "ingress"}:
        focus = {
            "csi_drivers": [item.get("metadata", {}).get("name") for item in csidrivers],
            "storage_classes": [item.get("metadata", {}).get("name") for item in storageclasses],
            "matching_system_workloads": [
                {"kind": item.get("kind"), "name": item.get("metadata", {}).get("name"), "namespace": item.get("metadata", {}).get("namespace")}
                for item in selected_workloads
            ],
        }
    else:
        focus = {"helm_releases": selected_helm, "matching_workloads": selected_workloads}

    return {
        "status": "operator_guided",
        "category": normalized,
        "resource_name": resource_name,
        "target_version": target_version,
        "focus": focus,
        "helm": {"status": "UNAVAILABLE" if helm_error else "REPORT", "error": helm_error, "release_count": len(helm_releases)},
        "writes_performed": False,
        "plan": [
            "Identify the owning Helm release, operator, or AKS-managed add-on from the inventory.",
            "Compare the installed version and manifest with the target Kubernetes compatibility matrix.",
            "Run helm upgrade --dry-run --debug or the vendor-provided compatibility check in a safe environment.",
            "Apply the smallest supported upgrade only after explicit authorization and verify workload readiness, CSI/CNI health, and API availability.",
        ],
        "required_authorization": "A separate explicit approval is required for the exact chart, operator, or add-on change.",
        "warnings": ["This planner does not upgrade Helm releases, operators, CSI/CNI, or ingress controllers."],
    }

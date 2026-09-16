"""Read-only CSI/CNI, add-on, Helm, and operator diagnostics."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, run_kubectl_json, run_kubectl_raw


def _items(batch: dict[str, tuple[int, str]], label: str) -> tuple[list[dict[str, Any]], list[str]]:
    entry = batch.get(label)
    if entry is None:
        return [], [f"{label}: no result returned in the batched output."]
    exit_code, raw = entry
    if exit_code != 0 or not raw.strip():
        return [], [f"{label}: kubectl query failed with exit code {exit_code}."]
    try:
        return json.loads(raw, strict=False).get("items", []), []
    except json.JSONDecodeError as exc:
        return [], [f"{label}: invalid JSON output: {exc}"]


def aks_check_platform_addons(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    target_kubernetes_version: str | None = None,
) -> dict[str, Any]:
    """Inventory CSI/CNI, system add-ons, Helm releases, and operator-like workloads read-only."""
    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "csidrivers": "get csidrivers",
            "csinodes": "get csinodes",
            "storageclasses": "get storageclass",
            "system_daemonsets": "get daemonset -n kube-system",
            "system_deployments": "get deployment -n kube-system",
            "operator_workloads": "get deployment,statefulset -A -l app.kubernetes.io/managed-by=Helm",
        },
    )
    query_errors: list[str] = []
    fallback_commands = {
        "csidrivers": "get csidrivers",
        "csinodes": "get csinodes",
        "storageclasses": "get storageclass",
        "system_daemonsets": "get daemonset -n kube-system",
        "system_deployments": "get deployment -n kube-system",
        "operator_workloads": "get deployment,statefulset -A -l app.kubernetes.io/managed-by=Helm",
    }

    def _read_items(label: str) -> list[dict[str, Any]]:
        parsed, errors = _items(batch, label)
        if not errors:
            return parsed
        try:
            return run_kubectl_json(subscription_id, resource_group, cluster_name, fallback_commands[label]).get("items", [])
        except Exception as exc:  # noqa: BLE001
            query_errors.extend(errors)
            query_errors.append(f"{label}: single-query fallback failed: {exc}")
            return []

    csidrivers = _read_items("csidrivers")
    csinodes = _read_items("csinodes")
    storageclasses = _read_items("storageclasses")
    daemonsets = _read_items("system_daemonsets")
    deployments = _read_items("system_deployments")
    operator_workloads = _read_items("operator_workloads")

    helm: dict[str, Any] = {"status": "UNAVAILABLE", "releases": []}
    try:
        raw_helm = run_kubectl_raw(subscription_id, resource_group, cluster_name, "helm ls -A -o json")
        releases = json.loads(raw_helm, strict=False)
        helm = {"status": "REPORT", "releases": releases if isinstance(releases, list) else []}
    except Exception as exc:  # noqa: BLE001
        helm["error"] = str(exc)
        query_errors.append(f"helm: query failed: {exc}")

    warnings: list[str] = []
    blockers: list[str] = []
    for item in daemonsets + deployments:
        status = item.get("status", {}) or {}
        desired = status.get("desiredNumberScheduled", status.get("replicas", 0)) or 0
        ready = status.get("numberReady", status.get("readyReplicas", 0)) or 0
        if desired != ready:
            warnings.append(f"System workload {item.get('metadata', {}).get('name')} is not fully ready ({ready}/{desired}).")
    for item in csidrivers:
        if not item.get("spec", {}).get("attachRequired", True):
            continue
    if not csidrivers:
        warnings.append("No CSIDriver objects were returned; CSI compatibility could not be confirmed.")
    if not storageclasses:
        warnings.append("No StorageClass objects were returned; storage provisioning compatibility could not be confirmed.")

    status = "BLOCKED" if blockers else ("INCOMPLETE" if query_errors else ("WARNING" if warnings else "PASS"))
    return {
        "status": status,
        "target_kubernetes_version": target_kubernetes_version,
        "csi_drivers": [
            {
                "name": item.get("metadata", {}).get("name"),
                "provisioner": item.get("spec", {}).get("driver"),
                "attach_required": item.get("spec", {}).get("attachRequired"),
                "pod_info_on_mount": item.get("spec", {}).get("podInfoOnMount"),
            }
            for item in csidrivers
        ],
        "csi_nodes": [item.get("metadata", {}).get("name") for item in csinodes],
        "storage_classes": [
            {
                "name": item.get("metadata", {}).get("name"),
                "provisioner": item.get("provisioner"),
                "reclaim_policy": item.get("reclaimPolicy"),
                "volume_binding_mode": item.get("volumeBindingMode"),
            }
            for item in storageclasses
        ],
        "system_workloads": [
            {"kind": item.get("kind"), "name": item.get("metadata", {}).get("name"), "namespace": item.get("metadata", {}).get("namespace")}
            for item in daemonsets + deployments
        ],
        "operator_workloads": [
            {"kind": item.get("kind"), "name": item.get("metadata", {}).get("name"), "namespace": item.get("metadata", {}).get("namespace")}
            for item in operator_workloads
        ],
        "helm": helm,
        "query_errors": query_errors,
        "blockers": blockers,
        "warnings": warnings,
        "operator_guided_steps": [
            "Compare CSI/CNI, ingress, kube-proxy, and system add-on versions with the target Kubernetes compatibility matrix.",
            "Review Helm chart and operator release notes before upgrading a release; use helm upgrade --dry-run --debug in a safe environment.",
            "Do not upgrade or replace an add-on from this inventory tool; use a dedicated, explicitly authorized remediation after compatibility is confirmed.",
        ],
        "run_command_invocations": 2,
    }

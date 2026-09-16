"""Read-only upgrade compatibility diagnostics for cluster infrastructure."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, run_kubectl_json


def _parse_batch(batch: dict[str, tuple[int, str]], label: str) -> tuple[list[dict[str, Any]], list[str]]:
    entry = batch.get(label)
    if entry is None:
        return [], [f"{label}: no result returned in the batched output."]
    exit_code, raw = entry
    if exit_code != 0:
        return [], [f"{label}: kubectl exited with code {exit_code}."]
    if not raw.strip():
        return [], [f"{label}: kubectl returned no JSON output."]
    try:
        payload = json.loads(raw, strict=False)
    except json.JSONDecodeError as exc:
        return [], [f"{label}: invalid JSON output: {exc}"]
    return payload.get("items", []), []


def _webhook_findings(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in items:
        metadata = item.get("metadata", {})
        for webhook in item.get("webhooks", []) or []:
            client = webhook.get("clientConfig", {}) or {}
            service = client.get("service", {}) or {}
            entry = {
                "configuration": metadata.get("name"),
                "webhook": webhook.get("name"),
                "service": service.get("name"),
                "namespace": service.get("namespace"),
                "url": client.get("url"),
                "has_ca_bundle": bool(client.get("caBundle")),
                "failure_policy": webhook.get("failurePolicy"),
            }
            findings.append(entry)
            if not entry["has_ca_bundle"]:
                warnings.append(
                    f"Webhook {entry['webhook']} has no embedded caBundle; verify its certificate source and service trust configuration."
                )
    return findings, warnings


def _crd_findings(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    for item in items:
        spec = item.get("spec", {}) or {}
        versions = spec.get("versions", []) or []
        storage_versions = [version.get("name") for version in versions if version.get("storage")]
        conversion = spec.get("conversion", {}) or {}
        entry = {
            "name": item.get("metadata", {}).get("name"),
            "versions": [version.get("name") for version in versions],
            "served_versions": [version.get("name") for version in versions if version.get("served")],
            "storage_versions": storage_versions,
            "conversion_strategy": conversion.get("strategy", "None"),
        }
        findings.append(entry)
        if len(storage_versions) != 1:
            warnings.append(f"CRD {entry['name']} has {len(storage_versions)} storage versions; review CRD versioning.")
        if len(entry["served_versions"]) > 1 and entry["conversion_strategy"] == "None":
            warnings.append(f"CRD {entry['name']} serves multiple versions without an explicit conversion strategy.")
    return findings, warnings


def aks_check_upgrade_compatibility(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    target_kubernetes_version: str | None = None,
) -> dict[str, Any]:
    """Inspect upgrade-sensitive infrastructure without changing cluster resources."""
    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "validating_webhooks": "get validatingwebhookconfigurations",
            "mutating_webhooks": "get mutatingwebhookconfigurations",
            "apiservices": "get apiservice",
            "crds": "get crd",
            "system_daemonsets": "get daemonset -n kube-system",
            "system_deployments": "get deployment -n kube-system",
            "nodes": "get nodes",
        },
    )

    query_errors: list[str] = []
    query_commands = {
        "validating_webhooks": "get validatingwebhookconfigurations",
        "mutating_webhooks": "get mutatingwebhookconfigurations",
        "apiservices": "get apiservice",
        "crds": "get crd",
        "system_daemonsets": "get daemonset -n kube-system",
        "system_deployments": "get deployment -n kube-system",
        "nodes": "get nodes",
    }

    def _items(label: str) -> list[dict[str, Any]]:
        parsed, errors = _parse_batch(batch, label)
        if not errors:
            return parsed
        try:
            payload = run_kubectl_json(subscription_id, resource_group, cluster_name, query_commands[label])
            return payload.get("items", [])
        except Exception as exc:  # noqa: BLE001
            query_errors.extend(errors)
            query_errors.append(f"{label}: single-query fallback failed: {exc}")
            return []

    validating = _items("validating_webhooks")
    mutating = _items("mutating_webhooks")
    api_services = _items("apiservices")
    crds = _items("crds")
    daemonsets = _items("system_daemonsets")
    deployments = _items("system_deployments")
    nodes = _items("nodes")

    webhook_findings, webhook_warnings = _webhook_findings(validating + mutating)
    crd_findings, crd_warnings = _crd_findings(crds)

    unavailable_api_services: list[dict[str, Any]] = []
    for item in api_services:
        conditions = item.get("status", {}).get("conditions", []) or []
        unavailable = [condition for condition in conditions if condition.get("type") == "Available" and condition.get("status") != "True"]
        if unavailable:
            unavailable_api_services.append({
                "name": item.get("metadata", {}).get("name"),
                "conditions": unavailable,
            })

    system_workloads: list[dict[str, Any]] = []
    workload_warnings: list[str] = []
    for kind, items in (("DaemonSet", daemonsets), ("Deployment", deployments)):
        for item in items:
            metadata = item.get("metadata", {})
            status = item.get("status", {}) or {}
            desired = status.get("desiredNumberScheduled", status.get("replicas", 0)) or 0
            ready = status.get("numberReady", status.get("readyReplicas", 0)) or 0
            entry = {"kind": kind, "name": metadata.get("name"), "desired": desired, "ready": ready}
            system_workloads.append(entry)
            if desired != ready:
                workload_warnings.append(f"{kind} kube-system/{entry['name']} is not fully ready ({ready}/{desired}).")

    node_findings: list[dict[str, Any]] = []
    node_warnings: list[str] = []
    for node in nodes:
        metadata = node.get("metadata", {})
        status = node.get("status", {}) or {}
        node_info = status.get("nodeInfo", {}) or {}
        conditions = {condition.get("type"): condition.get("status") for condition in status.get("conditions", []) or []}
        entry = {
            "name": metadata.get("name"),
            "kubelet_version": node_info.get("kubeletVersion"),
            "os_image": node_info.get("osImage"),
            "container_runtime": node_info.get("containerRuntimeVersion"),
            "ready": conditions.get("Ready") == "True",
            "conditions": conditions,
        }
        node_findings.append(entry)
        if not entry["ready"]:
            node_warnings.append(f"Node {entry['name']} is not Ready.")

    warnings = webhook_warnings + crd_warnings + workload_warnings + node_warnings
    blockers = [
        f"Aggregated APIService {item['name']} is unavailable."
        for item in unavailable_api_services
    ]
    if query_errors:
        warnings.append("Some compatibility queries could not be completed.")

    status = "BLOCKED" if blockers else ("INCOMPLETE" if query_errors and not warnings else ("WARNING" if warnings else "PASS"))
    return {
        "status": status,
        "target_kubernetes_version": target_kubernetes_version,
        "webhooks": webhook_findings,
        "unavailable_api_services": unavailable_api_services,
        "crds": crd_findings,
        "system_workloads": system_workloads,
        "nodes": node_findings,
        "query_errors": query_errors,
        "blockers": blockers,
        "warnings": warnings,
        "operator_guided_steps": [
            "Compare CSI, CNI, ingress, kube-proxy, operator, and node image versions with the target-version compatibility matrix.",
            "For webhook warnings, inspect the owning controller, service endpoints, CA bundle, and certificate expiry before changing admission configuration.",
            "For CRD warnings, upgrade the CRD and operator together and test conversion of existing custom resources.",
            "Do not apply a generic write from this diagnostic; use a dedicated remediation or an explicitly authorized operator-guided change.",
        ],
        "run_command_invocations": 1,
    }

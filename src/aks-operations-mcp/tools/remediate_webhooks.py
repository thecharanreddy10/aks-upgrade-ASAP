"""Read-only webhook certificate remediation planning."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, validate_k8s_name, validate_namespace


def _parse(batch: dict[str, tuple[int, str]], label: str) -> list[dict[str, Any]]:
    exit_code, raw = batch.get(label, (1, ""))
    if exit_code != 0 or not raw.strip():
        return []
    try:
        return json.loads(raw, strict=False).get("items", [])
    except json.JSONDecodeError:
        return []


def aks_plan_webhook_remediation(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    webhook_name: str,
    namespace: str | None = None,
) -> dict[str, Any]:
    """Inspect one admission webhook and return a safe certificate-repair plan without writes."""
    validate_k8s_name(webhook_name, "webhook configuration")
    if namespace:
        validate_namespace(namespace)

    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "validating": "get validatingwebhookconfigurations",
            "mutating": "get mutatingwebhookconfigurations",
            "services": f"get service -n {namespace}" if namespace else "get service -A",
            "endpoints": f"get endpoints -n {namespace}" if namespace else "get endpoints -A",
            "secrets": f"get secret -n {namespace}" if namespace else "get secret -A",
        },
    )

    configurations = _parse(batch, "validating") + _parse(batch, "mutating")
    matches = [item for item in configurations if item.get("metadata", {}).get("name") == webhook_name]
    if not matches:
        return {
            "status": "NOT_FOUND",
            "webhook_name": webhook_name,
            "writes_performed": False,
            "message": "Webhook configuration was not found in the requested cluster scope.",
        }

    webhook_entries: list[dict[str, Any]] = []
    service_names: set[tuple[str, str]] = set()
    for configuration in matches:
        for webhook in configuration.get("webhooks", []) or []:
            client = webhook.get("clientConfig", {}) or {}
            service = client.get("service", {}) or {}
            service_name = service.get("name")
            service_namespace = service.get("namespace")
            if service_name and service_namespace:
                service_names.add((service_namespace, service_name))
            webhook_entries.append({
                "configuration": webhook_name,
                "webhook": webhook.get("name"),
                "service": service_name,
                "namespace": service_namespace,
                "url": client.get("url"),
                "has_ca_bundle": bool(client.get("caBundle")),
                "failure_policy": webhook.get("failurePolicy"),
            })

    services = _parse(batch, "services")
    endpoints = _parse(batch, "endpoints")
    secrets = _parse(batch, "secrets")
    service_findings = [
        {
            "namespace": item.get("metadata", {}).get("namespace"),
            "name": item.get("metadata", {}).get("name"),
            "cluster_ip": item.get("spec", {}).get("clusterIP"),
            "ports": item.get("spec", {}).get("ports", []),
        }
        for item in services
        if (item.get("metadata", {}).get("namespace"), item.get("metadata", {}).get("name")) in service_names
    ]
    endpoint_findings = [
        {
            "namespace": item.get("metadata", {}).get("namespace"),
            "name": item.get("metadata", {}).get("name"),
            "subsets": item.get("subsets", []),
        }
        for item in endpoints
        if (item.get("metadata", {}).get("namespace"), item.get("metadata", {}).get("name")) in service_names
    ]
    secret_names = [item.get("metadata", {}).get("name") for item in secrets]
    has_endpoints = any(item.get("subsets") for item in endpoint_findings)
    ca_bundle_present = all(item["has_ca_bundle"] for item in webhook_entries)

    blockers: list[str] = []
    warnings: list[str] = []
    if not ca_bundle_present:
        blockers.append("Webhook configuration is missing a CA bundle; certificate trust cannot be confirmed.")
    if service_names and not has_endpoints:
        blockers.append("Webhook service has no ready endpoint evidence.")
    if not service_names and not any(item.get("url") for item in webhook_entries):
        blockers.append("Webhook has neither a service reference nor a URL.")
    if not secret_names:
        warnings.append("No namespace-scoped Secret inventory matched the requested scope; certificate ownership is not confirmed.")

    status = "BLOCKED" if blockers else ("WARNING" if warnings else "READY_FOR_OWNER_REVIEW")
    return {
        "status": status,
        "webhook_name": webhook_name,
        "webhooks": webhook_entries,
        "services": service_findings,
        "endpoints": endpoint_findings,
        "candidate_secret_names": secret_names,
        "blockers": blockers,
        "warnings": warnings,
        "writes_performed": False,
        "plan": [
            "Identify the owning controller or certificate manager from the webhook service and Secret metadata.",
            "Renew the certificate through its owning controller or certificate manager; do not patch caBundle blindly.",
            "Verify certificate validity, service endpoints, and an admission request after renewal.",
            "Re-run the upgrade compatibility and readiness diagnostics.",
        ],
        "write_policy": "This tool is planning-only. A separate explicitly authorized rotation tool is required before any write.",
        "run_command_invocations": 1,
    }

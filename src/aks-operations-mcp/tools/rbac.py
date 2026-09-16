"""Read-only RBAC and API aggregation diagnostics for AKS upgrades."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, run_kubectl_raw


def _items(batch: dict[str, tuple[int, str]], label: str) -> tuple[list[dict[str, Any]], list[str]]:
    exit_code, raw = batch.get(label, (1, ""))
    if exit_code != 0 or not raw.strip():
        return [], [f"{label}: query failed with exit code {exit_code}."]
    try:
        return json.loads(raw, strict=False).get("items", []), []
    except json.JSONDecodeError as exc:
        return [], [f"{label}: invalid JSON output: {exc}"]


def aks_check_rbac_api_health(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    namespace: str | None = None,
    service_account: str | None = None,
    checks: list[str] | None = None,
) -> dict[str, Any]:
    """Inspect aggregated APIs and optionally run explicit service-account permission checks."""
    checks = checks or ["get pods", "get deployments"]
    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "apiservices": "get apiservice",
            "rolebindings": f"get rolebindings -n {namespace}" if namespace else "get rolebindings -A",
            "clusterrolebindings": "get clusterrolebindings",
        },
    )
    api_services, api_errors = _items(batch, "apiservices")
    rolebindings, role_errors = _items(batch, "rolebindings")
    clusterrolebindings, clusterrole_errors = _items(batch, "clusterrolebindings")
    query_errors = api_errors + role_errors + clusterrole_errors

    unavailable_api_services = []
    for item in api_services:
        conditions = item.get("status", {}).get("conditions", []) or []
        unavailable = [condition for condition in conditions if condition.get("type") == "Available" and condition.get("status") != "True"]
        if unavailable:
            unavailable_api_services.append({"name": item.get("metadata", {}).get("name"), "conditions": unavailable})

    permission_checks: list[dict[str, Any]] = []
    if service_account:
        subject = service_account if ":" in service_account else f"system:serviceaccount:{namespace or 'default'}:{service_account}"
        for check in checks:
            command = f"auth can-i {check} --as={subject}"
            try:
                raw = run_kubectl_raw(subscription_id, resource_group, cluster_name, f"kubectl {command}")
                normalized = raw.strip().lower()
                context_error = "localhost:8080" in normalized or "connection refused" in normalized
                allowed = None if context_error else normalized.splitlines()[-1:] == ["yes"]
                if context_error:
                    query_errors.append(f"permission check {check}: Kubernetes API context was unavailable.")
                permission_checks.append({"subject": subject, "check": check, "allowed": allowed, "raw": raw.strip()[:2000]})
            except Exception as exc:  # noqa: BLE001
                query_errors.append(f"permission check {check}: {exc}")
                permission_checks.append({"subject": subject, "check": check, "allowed": None, "error": str(exc)})

    warnings = []
    blockers = [f"Aggregated APIService {item['name']} is unavailable." for item in unavailable_api_services]
    if service_account and any(item.get("allowed") is False for item in permission_checks):
        warnings.append(f"Service account {service_account} lacks one or more requested permissions.")
    if not service_account:
        warnings.append("No service account was supplied; RBAC permission checks were not run.")

    status = "BLOCKED" if blockers else ("INCOMPLETE" if query_errors else ("WARNING" if warnings else "PASS"))
    return {
        "status": status,
        "scope": {"namespace": namespace, "service_account": service_account},
        "unavailable_api_services": unavailable_api_services,
        "permission_checks": permission_checks,
        "rolebinding_count": len(rolebindings),
        "clusterrolebinding_count": len(clusterrolebindings),
        "query_errors": query_errors,
        "blockers": blockers,
        "warnings": warnings,
        "operator_guided_steps": [
            "Inspect the unavailable APIService backing service, endpoints, TLS, and owning extension server.",
            "Grant only the minimum Role, RoleBinding, ClusterRole, or ClusterRoleBinding required by the identified subject.",
            "Verify with kubectl auth can-i and re-run upgrade readiness; do not apply broad cluster-admin permissions as a shortcut.",
        ],
        "writes_performed": False,
        "run_command_invocations": 1 + len(permission_checks),
    }

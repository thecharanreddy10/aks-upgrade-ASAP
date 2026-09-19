"""Least-privilege RBAC remediation planning with no implicit writes."""

from __future__ import annotations

import re
from typing import Any

from tools.common import (
    assert_namespace_not_protected,
    require_remediation_approval,
    run_kubectl_raw,
    validate_k8s_name,
    validate_namespace,
)


_ALLOWED_VERBS = {"get", "list", "watch", "create", "update", "patch", "delete"}
_BLOCKED_ROLES = {"cluster-admin", "admin"}
_RESOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9.-]*(/[a-z0-9][a-z0-9.-]*)?$")


def _validate_plan_scope(namespace: str, service_account: str, role_name: str, resources: list[str], verbs: list[str]) -> None:
    validate_namespace(namespace)
    assert_namespace_not_protected(namespace)
    validate_k8s_name(service_account, "service account")
    validate_k8s_name(role_name, "role")
    if not resources or not all(isinstance(item, str) and _RESOURCE_RE.fullmatch(item) for item in resources):
        raise ValueError("resources must contain valid Kubernetes resource names.")
    if not verbs or not set(verbs) <= _ALLOWED_VERBS:
        raise ValueError(f"verbs must be selected from {sorted(_ALLOWED_VERBS)}.")
    if role_name.lower() in _BLOCKED_ROLES or "*" in resources or "*" in verbs:
        raise ValueError("Broad admin roles, wildcard resources, and wildcard verbs are not allowed.")


def _rbac_commands(namespace: str, service_account: str, role_name: str, resources: list[str], verbs: list[str]) -> tuple[str, str]:
    role_command = (
        f"kubectl create role {role_name} -n {namespace} "
        + " ".join(f"--verb={verb}" for verb in verbs)
        + " "
        + " ".join(f"--resource={resource}" for resource in resources)
        + " --dry-run=client -o yaml | kubectl apply -f -"
    )
    binding_command = (
        f"kubectl create rolebinding {role_name}-binding -n {namespace} "
        f"--role={role_name} --serviceaccount={namespace}:{service_account} --dry-run=client -o yaml | kubectl apply -f -"
    )
    return role_command, binding_command


def _verification_commands(namespace: str, service_account: str, role_name: str, resources: list[str], verbs: list[str]) -> list[str]:
    subject = f"system:serviceaccount:{namespace}:{service_account}"
    return [
        f"kubectl auth can-i {verb} {resource} -n {namespace} --as={subject}"
        for verb in verbs
        for resource in resources
    ] + [
        f"kubectl get role {role_name} -n {namespace} -o name",
        f"kubectl get rolebinding {role_name}-binding -n {namespace} -o name",
    ]


def aks_plan_rbac_remediation(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    namespace: str,
    service_account: str,
    role_name: str,
    resources: list[str],
    verbs: list[str],
    strategy: str = "role_binding",
) -> dict[str, Any]:
    """Return a least-privilege Role/RoleBinding plan without applying it."""
    _validate_plan_scope(namespace, service_account, role_name, resources, verbs)
    if strategy != "role_binding":
        raise ValueError("Only strategy='role_binding' is supported.")

    role_manifest = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "Role",
        "metadata": {"name": role_name, "namespace": namespace},
        "rules": [{"apiGroups": [""], "resources": resources, "verbs": verbs}],
    }
    binding_manifest = {
        "apiVersion": "rbac.authorization.k8s.io/v1",
        "kind": "RoleBinding",
        "metadata": {"name": f"{role_name}-binding", "namespace": namespace},
        "roleRef": {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": role_name},
        "subjects": [{"kind": "ServiceAccount", "name": service_account, "namespace": namespace}],
    }
    return {
        "status": "dry_run",
        "subscription_id": subscription_id,
        "resource_group": resource_group,
        "cluster_name": cluster_name,
        "namespace": namespace,
        "service_account": service_account,
        "strategy": strategy,
        "role": role_manifest,
        "role_binding": binding_manifest,
        "writes_performed": False,
        "authorization_required_to_apply": True,
        "verification": _verification_commands(namespace, service_account, role_name, resources, verbs),
        "warning": "This plan grants only the requested namespaced permissions. Review every resource and verb before authorizing application.",
    }


def aks_apply_rbac_remediation(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    namespace: str,
    service_account: str,
    role_name: str,
    resources: list[str],
    verbs: list[str],
    dry_run: bool = True,
    check_mode: str = "full",
    is_user_confirmed: bool = False,
) -> dict[str, Any]:
    """Apply an explicitly scoped least-privilege Role and RoleBinding, then verify them."""
    _validate_plan_scope(namespace, service_account, role_name, resources, verbs)
    role_command, binding_command = _rbac_commands(namespace, service_account, role_name, resources, verbs)
    if dry_run:
        return {
            "status": "dry_run",
            "writes_performed": False,
            "commands": [role_command, binding_command],
            "message": "Plan only; pass dry_run=False with check_mode='full' to apply after explicit authorization.",
        }

    if not is_user_confirmed:
        return {
            "status": "blocked",
            "writes_performed": False,
            "reason_code": "REMEDIATION_CONFIRMATION_REQUIRED",
            "message": "Applying this RBAC plan requires explicit confirmation of the exact displayed Role and RoleBinding plan.",
        }

    require_remediation_approval(check_mode, namespace=namespace)
    applied: list[str] = []
    try:
        for command in (role_command, binding_command):
            run_kubectl_raw(subscription_id, resource_group, cluster_name, command)
            applied.append(command)
        verification_outputs = []
        verification_errors = []
        for command in _verification_commands(namespace, service_account, role_name, resources, verbs):
            try:
                output = run_kubectl_raw(subscription_id, resource_group, cluster_name, command).strip()
                if "localhost:8080" in output or "connection refused" in output.lower():
                    verification_errors.append({"command": command, "error": output})
                verification_outputs.append({"command": command, "output": output})
            except Exception as exc:  # noqa: BLE001
                verification_errors.append({"command": command, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "writes_performed": bool(applied), "applied_commands": applied, "error": str(exc)}

    return {
        "status": "applied_unverified" if verification_errors else "applied",
        "writes_performed": True,
        "applied_commands": applied,
        "verification": verification_outputs,
        "verification_errors": verification_errors,
        "rollback": {"role_name": role_name, "role_binding_name": f"{role_name}-binding", "namespace": namespace},
    }


def aks_rollback_rbac_remediation(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    namespace: str,
    role_name: str,
    confirm_destructive: bool = False,
    dry_run: bool = True,
    check_mode: str = "full",
) -> dict[str, Any]:
    """Remove exactly the RoleBinding and Role created by an RBAC remediation."""
    validate_namespace(namespace)
    assert_namespace_not_protected(namespace)
    validate_k8s_name(role_name, "role")
    role_binding_name = f"{role_name}-binding"
    commands = [
        f"kubectl delete rolebinding {role_binding_name} -n {namespace}",
        f"kubectl delete role {role_name} -n {namespace}",
    ]
    if dry_run:
        return {"status": "dry_run", "writes_performed": False, "commands": commands}

    require_remediation_approval(check_mode, namespace=namespace, is_destructive=True, confirm_destructive=confirm_destructive)
    applied: list[str] = []
    try:
        for command in commands:
            run_kubectl_raw(subscription_id, resource_group, cluster_name, command)
            applied.append(command)
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "writes_performed": bool(applied), "applied_commands": applied, "error": str(exc)}
    return {"status": "rolled_back", "writes_performed": True, "applied_commands": applied}

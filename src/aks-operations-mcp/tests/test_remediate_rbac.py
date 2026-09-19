from __future__ import annotations

from tools import remediate_rbac


ARGS = ("sub", "rg", "cluster")


def test_rbac_planner_returns_namespaced_least_privilege_plan():
    result = remediate_rbac.aks_plan_rbac_remediation(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        role_name="api-read",
        resources=["pods"],
        verbs=["get", "list"],
    )

    assert result["status"] == "dry_run"
    assert result["writes_performed"] is False
    assert result["role"]["metadata"]["namespace"] == "phonebook"
    assert result["role"]["rules"][0]["verbs"] == ["get", "list"]
    assert result["role_binding"]["subjects"][0]["name"] == "api"


def test_rbac_planner_rejects_broad_permissions():
    for kwargs in (
        {"role_name": "cluster-admin", "resources": ["pods"], "verbs": ["get"]},
        {"role_name": "api", "resources": ["*"], "verbs": ["get"]},
        {"role_name": "api", "resources": ["pods"], "verbs": ["*"]},
    ):
        try:
            remediate_rbac.aks_plan_rbac_remediation(
                *ARGS,
                namespace="phonebook",
                service_account="api",
                **kwargs,
            )
        except ValueError:
            continue
        raise AssertionError("Expected broad RBAC permission to be rejected")


def test_rbac_planner_rejects_shell_unsafe_resource_tokens():
    try:
        remediate_rbac.aks_plan_rbac_remediation(
            *ARGS,
            namespace="phonebook",
            service_account="api",
            role_name="api-read",
            resources=["pods; echo compromised"],
            verbs=["get"],
        )
    except ValueError:
        return
    raise AssertionError("Expected shell-unsafe RBAC resource to be rejected")


def test_rbac_apply_defaults_to_dry_run(monkeypatch):
    monkeypatch.setattr(remediate_rbac, "run_kubectl_raw", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("write must not run")))

    result = remediate_rbac.aks_apply_rbac_remediation(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        role_name="api-read",
        resources=["pods"],
        verbs=["get"],
    )

    assert result["status"] == "dry_run"
    assert result["writes_performed"] is False


def test_rbac_apply_requires_write_gate(monkeypatch):
    monkeypatch.delenv("AKS_REMEDIATION_ENABLE_WRITE", raising=False)

    try:
        remediate_rbac.aks_apply_rbac_remediation(
            *ARGS,
            namespace="phonebook",
            service_account="api",
            role_name="api-read",
            resources=["pods"],
            verbs=["get"],
            dry_run=False,
                is_user_confirmed=True,
        )
    except PermissionError as exc:
        assert "disabled" in str(exc)
    else:
        raise AssertionError("Expected RBAC write gate to block apply")


def test_rbac_apply_requires_machine_verifiable_confirmation(monkeypatch):
    monkeypatch.setenv("AKS_REMEDIATION_ENABLE_WRITE", "true")

    result = remediate_rbac.aks_apply_rbac_remediation(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        role_name="api-read",
        resources=["pods"],
        verbs=["get"],
        dry_run=False,
        is_user_confirmed=False,
    )

    assert result["status"] == "blocked"
    assert result["reason_code"] == "REMEDIATION_CONFIRMATION_REQUIRED"
    assert result["writes_performed"] is False


def test_rbac_rollback_requires_destructive_confirmation(monkeypatch):
    monkeypatch.setenv("AKS_REMEDIATION_ENABLE_WRITE", "true")

    try:
        remediate_rbac.aks_rollback_rbac_remediation(
            *ARGS,
            namespace="phonebook",
            role_name="api-read",
            dry_run=False,
        )
    except PermissionError as exc:
        assert "permanently deletes" in str(exc)
    else:
        raise AssertionError("Expected destructive rollback confirmation")


def test_rbac_apply_verifies_each_permission_and_object(monkeypatch):
    monkeypatch.setenv("AKS_REMEDIATION_ENABLE_WRITE", "true")
    commands = []
    monkeypatch.setattr(remediate_rbac, "run_kubectl_raw", lambda *_args, **_kwargs: commands.append(_args[-1]) or "yes")

    result = remediate_rbac.aks_apply_rbac_remediation(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        role_name="api-read",
        resources=["pods", "deployments"],
        verbs=["get", "list"],
        dry_run=False,
        is_user_confirmed=True,
    )

    assert result["status"] == "applied"
    assert result["writes_performed"] is True
    assert any("auth can-i get pods" in command for command in commands)
    assert any("auth can-i list deployments" in command for command in commands)
    assert any("get rolebinding api-read-binding" in command for command in commands)


def test_rbac_apply_reports_context_failure_as_unverified(monkeypatch):
    monkeypatch.setenv("AKS_REMEDIATION_ENABLE_WRITE", "true")
    monkeypatch.setattr(
        remediate_rbac,
        "run_kubectl_raw",
        lambda *_args, **_kwargs: "connection to the server localhost:8080 was refused",
    )

    result = remediate_rbac.aks_apply_rbac_remediation(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        role_name="api-read",
        resources=["pods"],
        verbs=["get"],
        dry_run=False,
        is_user_confirmed=True,
    )

    assert result["status"] == "applied_unverified"
    assert result["writes_performed"] is True
    assert result["verification_errors"]

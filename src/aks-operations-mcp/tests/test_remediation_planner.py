from __future__ import annotations

from tools import resolve_upgrade_issue


ARGS = ("sub", "rg", "cluster")


def test_planner_returns_operator_guided_plan_without_writes():
    result = resolve_upgrade_issue.aks_plan_upgrade_issue_remediation(
        "webhook", *ARGS, strategy="renew_certificate"
    )

    assert result["status"] == "operator_guided"
    assert result["writes_performed"] is False
    assert result["operator_steps"]


def test_planner_dispatches_pod_dry_run(monkeypatch):
    monkeypatch.setattr(
        resolve_upgrade_issue,
        "aks_remediate_pods",
        lambda *args, **kwargs: {"status": "dry_run", "strategy": kwargs.get("strategy") or args[5]},
    )

    result = resolve_upgrade_issue.aks_plan_upgrade_issue_remediation(
        "pods", *ARGS, strategy="rollout_restart", namespace="phonebook", resource_name="web-123"
    )

    assert result["status"] == "dry_run"
    assert result["writes_performed"] is False
    assert result["plan"]["strategy"] == "rollout_restart"


def test_planner_requires_scope_for_pdb():
    try:
        resolve_upgrade_issue.aks_plan_upgrade_issue_remediation("pdb", *ARGS)
    except ValueError as exc:
        assert "namespace" in str(exc)
    else:
        raise AssertionError("Expected PDB scope validation to fail")

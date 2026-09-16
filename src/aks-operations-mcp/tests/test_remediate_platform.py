from __future__ import annotations

from tools import remediate_platform


ARGS = ("sub", "rg", "cluster")


def test_platform_planner_returns_operator_guided_helm_plan(monkeypatch):
    empty = '{"items":[]}'
    monkeypatch.setattr(remediate_platform, "run_kubectl_batch", lambda *_a, **_k: {
        "daemonsets": (0, empty),
        "deployments": (0, empty),
        "csidrivers": (0, empty),
        "storageclasses": (0, empty),
    })
    monkeypatch.setattr(remediate_platform, "run_kubectl_raw", lambda *_a, **_k: '[{"name":"phonebook","chart":"phonebook-1.2.3"}]')

    result = remediate_platform.aks_plan_platform_addon_remediation(*ARGS, category="helm", resource_name="phonebook", target_version="1.35.7")

    assert result["status"] == "operator_guided"
    assert result["helm"]["release_count"] == 1
    assert result["writes_performed"] is False
    assert result["required_authorization"]


def test_platform_planner_rejects_unknown_category():
    try:
        remediate_platform.aks_plan_platform_addon_remediation(*ARGS, category="backup")
    except ValueError as exc:
        assert "category" in str(exc)
    else:
        raise AssertionError("Expected unknown category to fail")

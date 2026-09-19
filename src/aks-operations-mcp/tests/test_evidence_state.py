"""Regression tests for fresh, current-run readiness semantics."""

import inspect

from tools import upgrade


ARGS = ("sub", "rg", "cluster")


def _install_healthy_checks(monkeypatch, calls):
    results = {
        "aks_check_node_health": {"unhealthy_nodes": []},
        "aks_check_pod_health": {"unhealthy_pods": [], "query_errors": []},
        "aks_check_pdb": {"is_upgrade_safe": True},
        "aks_check_storage": {"blockers": [], "warnings": []},
        "aks_check_deprecated_apis": {"blockers": [], "warnings": []},
    }

    for name, result in results.items():
        def check(*_args, _name=name, _result=result, **_kwargs):
            calls[_name] = calls.get(_name, 0) + 1
            return _result

        monkeypatch.setattr(upgrade, name, check)


def test_all_mandatory_checks_succeed_is_ready(monkeypatch):
    calls = {}
    _install_healthy_checks(monkeypatch, calls)

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert result["readiness"]["status"] == "READY"
    assert len(result["current_evidence"]) == 5
    assert all(count == 1 for count in calls.values())


def test_two_consecutive_readiness_runs_execute_fresh_checks(monkeypatch):
    calls = {}
    _install_healthy_checks(monkeypatch, calls)

    first = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")
    second = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert first["assessment_status"] == "READY"
    assert second["assessment_status"] == "READY"
    assert all(count == 2 for count in calls.values())
    assert "prior_evidence" not in inspect.signature(upgrade.aks_validate_upgrade_readiness).parameters
    assert "prior_evidence_reused" not in second
    assert "rejected_prior_evidence" not in second


def test_previous_ready_cannot_mask_current_failure(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    first = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")
    calls = {"node": 0}

    def failing_node(*_args, **_kwargs):
        calls["node"] += 1
        raise RuntimeError("node check unavailable")

    monkeypatch.setattr(upgrade, "aks_check_node_health", failing_node)
    second = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert first["assessment_status"] == "READY"
    assert second["assessment_status"] == "INCOMPLETE"
    assert second["readiness"]["is_ready"] is False
    assert calls["node"] == 2
    assert second["failed_unavailable_checks"][0]["check_type"] == "node_health"


def test_transient_failure_retry_success_is_ready(monkeypatch):
    calls = {"node": 0}
    _install_healthy_checks(monkeypatch, {})

    def transient_node(*_args, **_kwargs):
        calls["node"] += 1
        if calls["node"] == 1:
            raise RuntimeError("transient")
        return {"unhealthy_nodes": []}

    monkeypatch.setattr(upgrade, "aks_check_node_health", transient_node)
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert calls["node"] == 2


def test_persistent_unavailable_result_retries_once_then_is_incomplete(monkeypatch):
    calls = {"node": 0}
    _install_healthy_checks(monkeypatch, {})

    def unavailable_node(*_args, **_kwargs):
        calls["node"] += 1
        return {"query_errors": ["temporary outage"]}

    monkeypatch.setattr(upgrade, "aks_check_node_health", unavailable_node)
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert calls["node"] == 2
    assert result["assessment_status"] == "INCOMPLETE"
    assert result["readiness"]["is_ready"] is False


def test_current_blocker_is_blocked(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: {"unhealthy_nodes": [{"name": "node-1"}]})
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "BLOCKED"
    assert result["readiness"]["is_ready"] is False


def test_warning_only_current_result_is_warning(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    monkeypatch.setattr(upgrade, "aks_check_storage", lambda *_a, **_k: {"blockers": [], "warnings": ["watch storage"]})
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "WARNING"
    assert result["readiness"]["is_ready"] is True


def test_readiness_does_not_require_target_version(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert result["readiness"]["blockers"] == []


def test_readiness_contract_has_no_historical_evidence(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    parameters = inspect.signature(upgrade.aks_validate_upgrade_readiness).parameters
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert "prior_evidence" not in parameters
    for field in ("prior_evidence", "prior_evidence_reused", "rejected_prior_evidence", "validity_decision"):
        assert field not in result


def test_optional_failures_do_not_change_mandatory_status(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert "single_replica_health" not in result


def test_readiness_never_invokes_write_tools(monkeypatch):
    _install_healthy_checks(monkeypatch, {})
    writes = []
    monkeypatch.setattr(upgrade, "aks_kubectl_write", lambda *_a, **_k: writes.append("kubectl"), raising=False)
    monkeypatch.setattr(upgrade, "aks_az_write", lambda *_a, **_k: writes.append("az"), raising=False)
    upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert writes == []

"""Regression tests for deterministic assessment evidence semantics."""

from datetime import UTC, datetime, timedelta

from tools import upgrade
from tools.evidence import evidence_record, validate_prior_evidence


ARGS = ("sub", "rg", "cluster")


def _healthy_checks(monkeypatch, *, sequence=None):
    sequence = sequence or {}

    def install(name, value):
        def check(*_args, **_kwargs):
            sequence[name] = sequence.get(name, 0) + 1
            return value

        monkeypatch.setattr(upgrade, name, check)

    install("aks_check_node_health", {"unhealthy_nodes": []})
    install("aks_check_pod_health", {"unhealthy_pods": [], "query_errors": []})
    install("aks_check_pdb", {"is_upgrade_safe": True})
    install("aks_check_storage", {"blockers": [], "warnings": []})
    install("aks_check_deprecated_apis", {"blockers": [], "warnings": []})
    return sequence


def test_all_mandatory_checks_succeed_is_ready(monkeypatch):
    _healthy_checks(monkeypatch)

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert result["readiness"]["status"] == "READY"
    assert len(result["current_evidence"]) == 5


def test_mandatory_exception_retry_failure_is_incomplete(monkeypatch):
    sequence = _healthy_checks(monkeypatch)
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "INCOMPLETE"
    assert result["readiness"]["is_ready"] is False
    assert result["failed_unavailable_checks"][0]["check_type"] == "node_health"
    assert sequence["aks_check_pod_health"] == 1


def test_blocking_mandatory_result_is_blocked(monkeypatch):
    _healthy_checks(monkeypatch)
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: {"unhealthy_nodes": [{"name": "node-1"}]})

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "BLOCKED"
    assert result["readiness"]["is_ready"] is False


def test_optional_failures_do_not_change_mandatory_status(monkeypatch):
    _healthy_checks(monkeypatch)

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert "single_replica_health" not in result


def test_readiness_never_invokes_write_tools(monkeypatch):
    _healthy_checks(monkeypatch)
    writes = []
    monkeypatch.setattr(upgrade, "aks_kubectl_write", lambda *_a, **_k: writes.append("kubectl"), raising=False)
    monkeypatch.setattr(upgrade, "aks_az_write", lambda *_a, **_k: writes.append("az"), raising=False)

    upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert writes == []


def test_transient_exception_retry_success_is_ready(monkeypatch):
    sequence = {}

    def node_check(*_args, **_kwargs):
        sequence["node"] = sequence.get("node", 0) + 1
        if sequence["node"] == 1:
            raise RuntimeError("transient")
        return {"unhealthy_nodes": []}

    _healthy_checks(monkeypatch, sequence=sequence)
    monkeypatch.setattr(upgrade, "aks_check_node_health", node_check)

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert result["assessment_status"] == "READY"
    assert sequence["node"] == 2


def test_unavailable_result_retries_once_then_is_incomplete(monkeypatch):
    calls = {"node": 0}

    def node_check(*_args, **_kwargs):
        calls["node"] += 1
        return {"query_errors": ["temporary outage"]}

    _healthy_checks(monkeypatch)
    monkeypatch.setattr(upgrade, "aks_check_node_health", node_check)

    result = upgrade.aks_validate_upgrade_readiness(*ARGS, check_mode="full")

    assert calls["node"] == 2
    assert result["assessment_status"] == "INCOMPLETE"
    assert result["failed_unavailable_checks"][0]["check_type"] == "node_health"


def test_incomplete_readiness_blocks_preparation_even_when_target_is_available(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_available_upgrades",
        lambda *_a, **_k: {
            "lookup_mode": "upgrade-profile",
            "current_control_plane_version": "1.36.1",
            "current_node_pools": [],
            "control_plane_upgrades": [{"kubernetes_version": "1.36.2"}],
            "node_pool_upgrades": {},
            "node_pool_upgrade_profile_evidence": {},
            "upgrade_profile_errors": [],
        },
    )
    monkeypatch.setattr(
        upgrade,
        "aks_validate_upgrade_readiness",
        lambda *_a, **_k: {
            "assessment_status": "INCOMPLETE",
            "readiness": {"status": "INCOMPLETE", "is_ready": False, "blockers": [], "warnings": []},
        },
    )

    result = upgrade.aks_plan_upgrade_preparation(*ARGS, "1.36.2")

    assert result["target_validation"]["is_available"] is True
    assert result["assessment_status"] == "INCOMPLETE"
    assert result["status"] == "incomplete"


def test_valid_prior_evidence_is_explicitly_marked(monkeypatch):
    _healthy_checks(monkeypatch)
    prior = evidence_record(
        check_type="node_health",
        cluster_name="cluster",
        cluster_version="1.36.1",
        source_tool="aks_check_node_health",
        scope="all-namespaces",
        status="READY",
        result={"unhealthy_nodes": []},
    )
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))

    result = upgrade.aks_validate_upgrade_readiness(
        *ARGS,
        check_mode="full",
        current_cluster_version="1.36.1",
        prior_evidence=[prior],
    )

    assert result["assessment_status"] == "READY"
    assert result["prior_evidence_reused"][0]["evidence_id"] == prior["evidence_id"]
    assert result["failed_unavailable_checks"] == []


def test_stale_prior_evidence_is_rejected():
    prior = evidence_record(
        check_type="node_health",
        cluster_name="cluster",
        cluster_version="1.36.1",
        source_tool="aks_check_node_health",
        scope="all-namespaces",
        status="READY",
        valid_until=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )

    valid, reason = validate_prior_evidence(
        prior,
        cluster_name="cluster",
        cluster_version="1.36.1",
        scope="all-namespaces",
    )

    assert valid is False
    assert reason == "evidence_expired"


def test_cluster_version_change_invalidates_prior_evidence():
    prior = evidence_record(
        check_type="node_health",
        cluster_name="cluster",
        cluster_version="1.36.1",
        source_tool="aks_check_node_health",
        scope="all-namespaces",
        status="READY",
    )

    valid, reason = validate_prior_evidence(
        prior,
        cluster_name="cluster",
        cluster_version="1.36.2",
        scope="all-namespaces",
    )

    assert valid is False
    assert reason == "cluster_version_changed"


def test_current_failure_with_invalidated_prior_ready_evidence_is_incomplete(monkeypatch):
    _healthy_checks(monkeypatch)
    prior = evidence_record(
        check_type="node_health",
        cluster_name="cluster",
        cluster_version="1.36.1",
        source_tool="aks_check_node_health",
        scope="all-namespaces",
        status="READY",
        result={"unhealthy_nodes": []},
    )
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("down")))

    result = upgrade.aks_validate_upgrade_readiness(
        *ARGS,
        check_mode="full",
        current_cluster_version="1.36.2",
        prior_evidence=[prior],
    )

    assert result["assessment_status"] == "INCOMPLETE"
    assert result["readiness"]["is_ready"] is False
    assert result["prior_evidence_reused"] == []
    assert result["rejected_prior_evidence"][0]["reason"] == "cluster_version_changed"


def test_remediation_and_upgrade_invalidate_prior_evidence():
    prior = evidence_record(
        check_type="node_health",
        cluster_name="cluster",
        cluster_version="1.36.1",
        source_tool="aks_check_node_health",
        scope="all-namespaces",
        status="READY",
    )

    assert validate_prior_evidence(prior, cluster_name="cluster", cluster_version="1.36.1", scope="all-namespaces", remediation_performed=True)[1] == "remediation_performed"
    assert validate_prior_evidence(prior, cluster_name="cluster", cluster_version="1.36.1", scope="all-namespaces", upgrade_performed=True)[1] == "upgrade_executed"
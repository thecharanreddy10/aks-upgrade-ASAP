"""Tests for the additional upgrade-readiness validation tools."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

from tools import upgrade, validation
from tools.validation import (
    aks_check_node_pool_surge,
    aks_check_operator_health,
    aks_check_priority_class,
    aks_check_single_replica_services,
)

CLUSTER_ARGS = ("sub-id", "rg", "cluster")


def test_single_replica_services_warn_for_one_replica(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"cerebral","name":"cp-api"},'
            '"spec":{"replicas":1,"selector":{"matchLabels":{"app":"cp-api"}}},'
            '"status":{"availableReplicas":1}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_single_replica_services(*CLUSTER_ARGS, namespace="cerebral", label_selector="app=cp-api")

    assert result["status"] == "WARNING"
    assert len(result["single_replica_workloads"]) == 1
    assert result["single_replica_workloads"][0]["name"] == "cp-api"


def test_single_replica_services_pass_for_two_replicas(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"cerebral","name":"cp-api"},'
            '"spec":{"replicas":2,"selector":{"matchLabels":{"app":"cp-api"}}},'
            '"status":{"availableReplicas":2}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_single_replica_services(*CLUSTER_ARGS, namespace="cerebral", label_selector="app=cp-api")

    assert result["status"] == "PASS"
    assert result["single_replica_workloads"] == []


def test_single_replica_services_namespace_only_warns_for_one_replica(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"phonebook","name":"api"},'
            '"spec":{"replicas":1},"status":{"availableReplicas":1}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_single_replica_services(*CLUSTER_ARGS, namespace="phonebook")

    assert result["status"] == "WARNING"
    assert result["matched_workloads"][0]["name"] == "api"
    assert result["single_replica_workloads"][0]["name"] == "api"


def test_single_replica_services_namespace_only_passes_for_two_replicas(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"phonebook","name":"api"},'
            '"spec":{"replicas":2},"status":{"availableReplicas":2}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_single_replica_services(*CLUSTER_ARGS, namespace="phonebook")

    assert result["status"] == "PASS"
    assert result["single_replica_workloads"] == []


def test_single_replica_services_namespace_only_is_incomplete_on_query_failure(monkeypatch):
    batch = {
        "deployments": (1, ""),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_single_replica_services(*CLUSTER_ARGS, namespace="phonebook")

    assert result["status"] == "INCOMPLETE"
    assert result["query_errors"]


def test_single_replica_services_is_not_configured_without_selector():
    result = aks_check_single_replica_services(*CLUSTER_ARGS)

    assert result["status"] == "NOT_CONFIGURED"


def test_operator_health_skips_non_sit():
    result = aks_check_operator_health(*CLUSTER_ARGS, environment="PROD", operator_selector="app=operator")

    assert result["status"] == "SKIPPED"


def test_operator_health_not_configured_without_selector():
    result = aks_check_operator_health(*CLUSTER_ARGS, environment="SIT")

    assert result["status"] == "NOT_CONFIGURED"


def test_post_upgrade_smoke_checks_pass_after_complete_cluster_upgrade(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_upgrade_execution_status",
        lambda *_a: {
            "cluster": {
                "kubernetes_version": "1.30.1",
                "current_kubernetes_version": "1.30.1",
                "provisioning_state": "Succeeded",
            },
            "node_pools": [
                {
                    "name": "userpool",
                    "orchestrator_version": "1.30.1",
                    "current_orchestrator_version": "1.30.1",
                    "provisioning_state": "Succeeded",
                }
            ],
        },
    )
    monkeypatch.setattr(
        upgrade,
        "aks_validate_upgrade_readiness",
        lambda *_a, **_k: {"readiness": {"is_ready": True, "blockers": [], "warnings": []}},
    )

    result = upgrade.aks_run_post_upgrade_smoke_checks(*CLUSTER_ARGS, "1.30.1")

    assert result["status"] == "PASS"
    assert [item["status"] for item in result["version_checks"]] == ["PASS", "PASS"]


def test_post_upgrade_smoke_checks_block_on_node_pool_version_mismatch(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_upgrade_execution_status",
        lambda *_a: {
            "cluster": {
                "kubernetes_version": "1.30.1",
                "current_kubernetes_version": "1.30.1",
                "provisioning_state": "Succeeded",
            },
            "node_pools": [
                {
                    "name": "userpool",
                    "orchestrator_version": "1.29.3",
                    "current_orchestrator_version": "1.29.3",
                    "provisioning_state": "Succeeded",
                }
            ],
        },
    )
    monkeypatch.setattr(
        upgrade,
        "aks_validate_upgrade_readiness",
        lambda *_a, **_k: {"readiness": {"is_ready": True, "blockers": [], "warnings": []}},
    )

    result = upgrade.aks_run_post_upgrade_smoke_checks(
        *CLUSTER_ARGS,
        "1.30.1",
        stage="node_pool",
        node_pool_name="userpool",
    )

    assert result["status"] == "BLOCKED"
    assert result["version_checks"][0]["status"] == "BLOCKED"
    assert "node_pool 'userpool'" in result["blockers"][0]


def test_post_upgrade_smoke_checks_use_fresh_readiness(monkeypatch):
    readiness_calls = []
    readiness_results = [
        {"assessment_status": "READY", "readiness": {"is_ready": True, "blockers": [], "warnings": []}},
        {"assessment_status": "INCOMPLETE", "readiness": {"is_ready": False, "blockers": [], "warnings": []}},
    ]
    monkeypatch.setattr(
        upgrade,
        "aks_get_upgrade_execution_status",
        lambda *_a: {
            "cluster": {
                "current_kubernetes_version": "1.30.1",
                "kubernetes_version": "1.30.1",
                "provisioning_state": "Succeeded",
            },
            "node_pools": [],
        },
    )

    def fresh_readiness(*_args, **_kwargs):
        readiness_calls.append(_kwargs)
        return readiness_results.pop(0)

    monkeypatch.setattr(upgrade, "aks_validate_upgrade_readiness", fresh_readiness)

    pre_upgrade = upgrade.aks_validate_upgrade_readiness(*CLUSTER_ARGS, check_mode="full")
    result = upgrade.aks_run_post_upgrade_smoke_checks(
        *CLUSTER_ARGS,
        "1.30.1",
        stage="control_plane",
    )

    assert pre_upgrade["assessment_status"] == "READY"
    assert len(readiness_calls) == 2
    assert result["readiness"]["assessment_status"] == "INCOMPLETE"
    assert result["status"] == "INCOMPLETE"


def test_post_upgrade_smoke_checks_propagate_real_readiness_blocker(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_upgrade_execution_status",
        lambda *_a: {
            "cluster": {"current_kubernetes_version": "1.30.1", "provisioning_state": "Succeeded"},
            "node_pools": [],
        },
    )
    monkeypatch.setattr(
        upgrade,
        "aks_validate_upgrade_readiness",
        lambda *_a, **_k: {
            "assessment_status": "BLOCKED",
            "readiness": {"status": "BLOCKED", "is_ready": False, "blockers": ["PDB blocked"], "warnings": []},
        },
    )

    result = upgrade.aks_run_post_upgrade_smoke_checks(*CLUSTER_ARGS, "1.30.1", stage="control_plane")

    assert result["status"] == "BLOCKED"
    assert result["blockers"] == ["PDB blocked"]


def test_post_upgrade_smoke_checks_preserve_readiness_warning(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_upgrade_execution_status",
        lambda *_a: {
            "cluster": {"current_kubernetes_version": "1.30.1", "provisioning_state": "Succeeded"},
            "node_pools": [],
        },
    )
    monkeypatch.setattr(
        upgrade,
        "aks_validate_upgrade_readiness",
        lambda *_a, **_k: {
            "assessment_status": "WARNING",
            "readiness": {"status": "WARNING", "is_ready": True, "blockers": [], "warnings": ["watch storage"]},
        },
    )

    result = upgrade.aks_run_post_upgrade_smoke_checks(*CLUSTER_ARGS, "1.30.1", stage="control_plane")

    assert result["status"] == "WARNING"
    assert result["blockers"] == []
    assert result["warnings"] == ["watch storage"]


def test_collect_pre_upgrade_inventory_reports_cluster_and_kubectl_facts(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_cluster_details",
        lambda *_a, **_k: {"kubernetes_version": "1.31.100", "provisioning_state": "Succeeded"},
    )
    monkeypatch.setattr(
        upgrade,
        "aks_get_node_pools",
        lambda *_a, **_k: {"node_pools": [{"name": "userpool", "orchestrator_version": "1.31.100"}]},
    )

    def fake_run_kubectl_batch(*_args, **_kwargs):
        return {
            "kube_version": (0, '{"clientVersion":{"gitVersion":"v1.31.2"}}'),
            "nodes": (0, '{"items":[{"metadata":{"name":"node-1"},"status":{"conditions":[{"type":"Ready","status":"True"}]} }]}'),
            "pods": (0, '{"items":[{"metadata":{"name":"api","namespace":"default"},"status":{"phase":"Running"} }]}'),
            "pvcs": (0, '{"items":[] }'),
            "pvs": (0, '{"items":[] }'),
            "crds": (0, '{"items":[{"metadata":{"name":"widgets.example.com"}}]}'),
        }

    monkeypatch.setattr(upgrade, "run_kubectl_batch", fake_run_kubectl_batch)
    monkeypatch.setattr(upgrade, "run_kubectl_raw", lambda *_a, **_k: "NAME\tNAMESPACE\nteam-a\tdefault\n")
    monkeypatch.setattr(
        upgrade,
        "aks_check_storage",
        lambda *_a, **_k: {
            "storage_health": "HEALTHY",
            "blockers": [],
            "warnings": [],
            "query_errors": [],
            "recommendations": ["No storage issues detected."],
        },
    )

    result = upgrade.aks_collect_pre_upgrade_inventory(*CLUSTER_ARGS)

    assert result["status"] == "PASS"
    assert result["inventory"]["cluster"]["kubernetes_version"] == "1.31.100"
    assert result["inventory"]["kubectl_version"]["client_version"] == "v1.31.2"
    assert result["inventory"]["nodes"]["total_nodes"] == 1
    assert result["inventory"]["pods"]["total_pods"] == 1
    assert result["inventory"]["helm"]["status"] == "REPORT"
    assert result["inventory"]["nodes"]["ready_nodes"] == 1
    assert result["inventory"]["nodes"]["items"] == []
    assert result["inventory"]["pods"]["unhealthy"] == []
    assert "status" not in result["inventory"]["pods"]["unhealthy"]
    assert result["inventory"]["crds"]["items"] == []


def test_collect_pre_upgrade_inventory_marks_helm_query_failure(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_cluster_details",
        lambda *_a, **_k: {"kubernetes_version": "1.31.100", "provisioning_state": "Succeeded"},
    )
    monkeypatch.setattr(
        upgrade,
        "aks_get_node_pools",
        lambda *_a, **_k: {"node_pools": [{"name": "userpool", "orchestrator_version": "1.31.100"}]},
    )

    def fake_run_kubectl_batch(*_args, **_kwargs):
        return {
            "kube_version": (0, '{"clientVersion":{"gitVersion":"v1.31.2"}}'),
            "nodes": (0, '{"items":[]}'),
            "pods": (0, '{"items":[]}'),
            "pvcs": (0, '{"items":[]}'),
            "pvs": (0, '{"items":[]}'),
            "crds": (0, '{"items":[]}'),
        }

    monkeypatch.setattr(upgrade, "run_kubectl_batch", fake_run_kubectl_batch)
    monkeypatch.setattr(upgrade, "run_kubectl_raw", lambda *_a, **_k: "helm: command not found")

    result = upgrade.aks_collect_pre_upgrade_inventory(*CLUSTER_ARGS)

    assert result["status"] == "WARN"
    assert result["inventory"]["helm"]["status"] == "UNAVAILABLE"
    assert "helm" in " ".join(result["warnings"]).lower()


def test_collect_pre_upgrade_inventory_reports_storage_validation(monkeypatch):
    monkeypatch.setattr(
        upgrade,
        "aks_get_cluster_details",
        lambda *_a, **_k: {"kubernetes_version": "1.31.100", "provisioning_state": "Succeeded"},
    )
    monkeypatch.setattr(
        upgrade,
        "aks_get_node_pools",
        lambda *_a, **_k: {"node_pools": [{"name": "userpool", "orchestrator_version": "1.31.100"}]},
    )

    def fake_run_kubectl_batch(*_args, **_kwargs):
        return {
            "kube_version": (0, '{"clientVersion":{"gitVersion":"v1.31.2"}}'),
            "nodes": (0, '{"items":[]}'),
            "pods": (0, '{"items":[]}'),
            "pvcs": (0, '{"items":[]}'),
            "pvs": (0, '{"items":[]}'),
            "crds": (0, '{"items":[]}'),
        }

    monkeypatch.setattr(upgrade, "run_kubectl_batch", fake_run_kubectl_batch)
    monkeypatch.setattr(upgrade, "run_kubectl_raw", lambda *_a, **_k: "NAME\tNAMESPACE\nteam-a\tdefault\n")
    monkeypatch.setattr(
        upgrade,
        "aks_check_storage",
        lambda *_a, **_k: {
            "storage_health": "WARNING",
            "blockers": [],
            "warnings": ["PVC default/cache is Pending"],
            "query_errors": [],
            "recommendations": ["Monitor PVC state"],
        },
    )

    result = upgrade.aks_collect_pre_upgrade_inventory(*CLUSTER_ARGS)

    assert result["status"] == "WARN"
    assert result["inventory"]["storage_validation"]["storage_health"] == "WARNING"
    assert "pvc default/cache" in " ".join(result["warnings"]).lower()


def test_operator_health_blocks_unhealthy_operator(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"sit-ops","name":"sample-operator",'
            '"labels":{"app.kubernetes.io/version":"1.2.3"}},'
            '"spec":{"replicas":2},"status":{"availableReplicas":1},'
            '"template":{"spec":{"containers":[{"image":"example/operator:1.2.3"}]}}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_operator_health(
        *CLUSTER_ARGS,
        environment="SIT",
        namespace="sit-ops",
        operator_selector="app=sample-operator",
    )

    assert result["status"] == "BLOCKED"
    assert result["unhealthy_operators"][0]["available_replicas"] == 1
    assert result["operators"][0]["current_version"] == "1.2.3"
    assert result["summary"] == {
        "status": "BLOCKED",
        "operators_checked": 1,
        "healthy_operators": 0,
        "unhealthy_operators": 1,
        "version_mismatches": 0,
        "query_errors": 0,
    }


def test_operator_health_passes_healthy_operator_and_matches_target(monkeypatch):
    batch = {
        "deployments": (
            0,
            '{"items":[{"metadata":{"namespace":"sit-ops","name":"sample-operator",'
            '"labels":{"app.kubernetes.io/version":"1.2.3"}},'
            '"spec":{"replicas":1},"status":{"availableReplicas":1},'
            '"template":{"spec":{"containers":[{"image":"example/operator:1.2.3"}]}}}]}',
        ),
        "statefulsets": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(validation, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = aks_check_operator_health(
        *CLUSTER_ARGS,
        environment="SIT",
        namespace="sit-ops",
        operator_selector="app=sample-operator",
        target_version="1.2.3",
    )

    assert result["status"] == "PASS"
    assert result["version_mismatches"] == []


def test_service_ingress_url_check_reports_service_ingress_and_http_success(monkeypatch):
    monkeypatch.setattr(
        validation,
        "run_kubectl_batch",
        lambda *_a, **_k: {
            "services": (
                0,
                '{"items":[{"metadata":{"namespace":"default","name":"web"},'
                '"spec":{"type":"LoadBalancer","clusterIP":"10.0.0.8",'
                '"ports":[{"port":80}]},"status":{"loadBalancer":{"ingress":[{"ip":"203.0.113.10"}]}}}]}',
            ),
            "ingresses": (
                0,
                '{"items":[{"metadata":{"namespace":"default","name":"web-ingress"},'
                '"spec":{"rules":[{"host":"app.example.com"}]},'
                '"status":{"loadBalancer":{"ingress":[{"hostname":"app.example.com"}]}}}]}',
            ),
        },
    )
    monkeypatch.setattr(validation, "run_kubectl_raw", lambda *_a, **_k: "200")

    result = validation.aks_check_service_ingress_urls(
        *CLUSTER_ARGS,
        namespace="default",
        service_name="web",
        ingress_name="web-ingress",
        url="https://app.example.com/health",
    )

    assert result["status"] == "PASS"
    assert result["services"][0]["external_endpoints"] == ["203.0.113.10"]
    assert result["ingresses"][0]["hosts"] == ["app.example.com"]
    assert result["url_probe"]["http_status"] == 200


def test_service_ingress_url_check_rejects_unsafe_url(monkeypatch):
    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("Cluster commands must not run for an invalid URL.")

    monkeypatch.setattr(validation, "run_kubectl_batch", unexpected_call)

    try:
        validation.aks_check_service_ingress_urls(*CLUSTER_ARGS, url="ftp://example.com/health")
    except ValueError as exc:
        assert "absolute http" in str(exc)
    else:
        raise AssertionError("Expected invalid URL to be rejected.")


def test_node_pool_surge_warns_for_ten_node_pool_below_recommendation(monkeypatch):
    pool = SimpleNamespace(
        name="userpool",
        mode="User",
        count=10,
        upgrade_settings=SimpleNamespace(max_surge="10%"),
    )
    fake_client = SimpleNamespace(agent_pools=SimpleNamespace(list=lambda *_a, **_k: [pool]))
    monkeypatch.setattr(validation, "get_container_service_client", lambda *_a, **_k: fake_client)

    result = aks_check_node_pool_surge(*CLUSTER_ARGS)

    assert result["status"] == "WARNING"
    assert result["recommendations"][0]["recommended_max_surge"] == "33%"
    assert result["node_pools"][0]["parsed_max_surge"]["surge_nodes"] == 1


def test_node_pool_surge_passes_for_33_percent(monkeypatch):
    pool = SimpleNamespace(
        name="userpool",
        mode="User",
        count=10,
        upgrade_settings=SimpleNamespace(max_surge="33%"),
    )
    fake_client = SimpleNamespace(agent_pools=SimpleNamespace(list=lambda *_a, **_k: [pool]))
    monkeypatch.setattr(validation, "get_container_service_client", lambda *_a, **_k: fake_client)

    result = aks_check_node_pool_surge(*CLUSTER_ARGS)

    assert result["status"] == "PASS"
    assert result["recommendations"] == []


def test_node_pool_surge_accepts_numeric_four_as_equivalent_capacity(monkeypatch):
    pool = SimpleNamespace(
        name="userpool",
        mode="User",
        count=10,
        upgrade_settings=SimpleNamespace(max_surge="4"),
    )
    fake_client = SimpleNamespace(agent_pools=SimpleNamespace(list=lambda *_a, **_k: [pool]))
    monkeypatch.setattr(validation, "get_container_service_client", lambda *_a, **_k: fake_client)

    result = aks_check_node_pool_surge(*CLUSTER_ARGS)

    assert result["status"] == "PASS"


def test_node_pool_surge_is_incomplete_when_no_user_pools_are_found(monkeypatch):
    pools = [SimpleNamespace(name="systempool", mode="System", count=3)]
    fake_client = SimpleNamespace(agent_pools=SimpleNamespace(list=lambda *_a, **_k: pools))
    monkeypatch.setattr(validation, "get_container_service_client", lambda *_a, **_k: fake_client)

    result = aks_check_node_pool_surge(*CLUSTER_ARGS)

    assert result["status"] == "INCOMPLETE"
    assert result["user_pools_checked"] == 0
    assert result["node_pools"] == []


def test_priority_class_warns_for_non_compliant_critical_pod(monkeypatch):
    payload = {
        "items": [
            {
                "metadata": {"namespace": "kube-system", "name": "critical-agent"},
                "spec": {"priorityClassName": "system-node-critical"},
            }
        ]
    }
    monkeypatch.setattr(validation, "run_kubectl_json", lambda *_a, **_k: payload)

    result = aks_check_priority_class(
        *CLUSTER_ARGS,
        namespace="kube-system",
        critical_selector="app=critical-agent",
    )

    assert result["status"] == "WARNING"
    assert result["violations"][0]["priority_class"] == "system-node-critical"


def test_priority_class_passes_for_system_cluster_critical(monkeypatch):
    payload = {
        "items": [
            {
                "metadata": {"namespace": "kube-system", "name": "critical-agent"},
                "spec": {"priorityClassName": "system-cluster-critical"},
            }
        ]
    }
    monkeypatch.setattr(validation, "run_kubectl_json", lambda *_a, **_k: payload)

    result = aks_check_priority_class(
        *CLUSTER_ARGS,
        namespace="kube-system",
        critical_selector="app=critical-agent",
    )

    assert result["status"] == "PASS"
    assert result["violations"] == []


def test_validate_upgrade_readiness_runs_only_mandatory_checks(monkeypatch):
    healthy = {"unhealthy_nodes": []}
    pod_health = {"unhealthy_pods": [], "query_errors": []}
    pdb_health = {"is_upgrade_safe": True}
    storage_health = {"blockers": [], "warnings": []}
    deprecated_health = {"blockers": [], "warnings": []}

    mandatory_calls = []

    def mandatory_result(name, result):
        def check(*_args, **_kwargs):
            mandatory_calls.append(name)
            return result

        return check

    monkeypatch.setattr(upgrade, "aks_check_node_health", mandatory_result("node_health", healthy))
    monkeypatch.setattr(upgrade, "aks_check_pod_health", mandatory_result("pod_health", pod_health))
    monkeypatch.setattr(upgrade, "aks_check_pdb", mandatory_result("pdb_health", pdb_health))
    monkeypatch.setattr(upgrade, "aks_check_storage", mandatory_result("storage_health", storage_health))
    monkeypatch.setattr(upgrade, "aks_check_deprecated_apis", mandatory_result("deprecated_api_health", deprecated_health))

    def unexpected_optional_call(*_args, **_kwargs):
        raise AssertionError("Optional validation was called by mandatory readiness.")

    for name in (
        "aks_check_single_replica_services",
        "aks_check_operator_health",
        "aks_check_node_pool_surge",
        "aks_check_priority_class",
    ):
        monkeypatch.setattr(upgrade, name, unexpected_optional_call, raising=False)

    result = upgrade.aks_validate_upgrade_readiness(*CLUSTER_ARGS, check_mode="full")

    assert result["readiness"]["is_ready"] is True
    assert result["deep_check_errors"] == []
    assert sorted(mandatory_calls) == [
        "deprecated_api_health",
        "node_health",
        "pdb_health",
        "pod_health",
        "storage_health",
    ]
    assert all(name not in result for name in (
        "single_replica_health",
        "operator_health",
        "node_pool_surge_health",
        "priority_class_health",
    ))


def test_validate_upgrade_readiness_public_contract_is_current_run_only(monkeypatch):
    healthy = {"unhealthy_nodes": []}
    pod_health = {"unhealthy_pods": [], "query_errors": []}
    pdb_health = {"is_upgrade_safe": True}
    storage_health = {"blockers": [], "warnings": []}
    deprecated_health = {"blockers": [], "warnings": []}
    monkeypatch.setattr(upgrade, "aks_check_node_health", lambda *_a, **_k: healthy)
    monkeypatch.setattr(upgrade, "aks_check_pod_health", lambda *_a, **_k: pod_health)
    monkeypatch.setattr(upgrade, "aks_check_pdb", lambda *_a, **_k: pdb_health)
    monkeypatch.setattr(upgrade, "aks_check_storage", lambda *_a, **_k: storage_health)
    monkeypatch.setattr(upgrade, "aks_check_deprecated_apis", lambda *_a, **_k: deprecated_health)

    parameters = inspect.signature(upgrade.aks_validate_upgrade_readiness).parameters
    result = upgrade.aks_validate_upgrade_readiness(*CLUSTER_ARGS, check_mode="full")

    assert parameters["target_kubernetes_version"].default is None
    assert "prior_evidence" not in parameters
    assert "prior_evidence_reused" not in result
    assert "rejected_prior_evidence" not in result
    assert len(result["current_evidence"]) == 5
    assert all(item["evidence_id"].startswith("EV-") for item in result["current_evidence"])
    assert all(item["timestamp"] == item["last_verified_at"] for item in result["current_evidence"])

from __future__ import annotations

from tools import rbac


ARGS = ("sub", "rg", "cluster")


def test_rbac_reports_unavailable_api_service_and_permission_gap(monkeypatch):
    batch = {
        "apiservices": (0, '{"items":[{"metadata":{"name":"v1beta1.metrics.k8s.io"},"status":{"conditions":[{"type":"Available","status":"False"}]}}]}'),
        "rolebindings": (0, '{"items":[]}'),
        "clusterrolebindings": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(rbac, "run_kubectl_batch", lambda *_a, **_k: batch)
    monkeypatch.setattr(rbac, "run_kubectl_raw", lambda *_a, **_k: "no")

    result = rbac.aks_check_rbac_api_health(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        checks=["get pods"],
    )

    assert result["status"] == "BLOCKED"
    assert result["unavailable_api_services"][0]["name"] == "v1beta1.metrics.k8s.io"
    assert result["permission_checks"][0]["allowed"] is False
    assert result["writes_performed"] is False


def test_rbac_without_subject_is_advisory(monkeypatch):
    empty = '{"items":[]}'
    monkeypatch.setattr(rbac, "run_kubectl_batch", lambda *_a, **_k: {
        "apiservices": (0, empty),
        "rolebindings": (0, empty),
        "clusterrolebindings": (0, empty),
    })

    result = rbac.aks_check_rbac_api_health(*ARGS)

    assert result["status"] == "WARNING"
    assert result["permission_checks"] == []
    assert result["warnings"]


def test_rbac_context_failure_is_incomplete_not_denied(monkeypatch):
    empty = '{"items":[]}'
    monkeypatch.setattr(rbac, "run_kubectl_batch", lambda *_a, **_k: {
        "apiservices": (0, empty),
        "rolebindings": (0, empty),
        "clusterrolebindings": (0, empty),
    })
    monkeypatch.setattr(rbac, "run_kubectl_raw", lambda *_a, **_k: "The connection to the server localhost:8080 was refused")

    result = rbac.aks_check_rbac_api_health(
        *ARGS,
        namespace="phonebook",
        service_account="api",
        checks=["get pods"],
    )

    assert result["status"] == "INCOMPLETE"
    assert result["permission_checks"][0]["allowed"] is None
    assert result["query_errors"]

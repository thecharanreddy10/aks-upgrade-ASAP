from __future__ import annotations

from tools import compatibility


ARGS = ("sub", "rg", "cluster")


def test_upgrade_compatibility_reports_webhook_crd_and_node_findings(monkeypatch):
    batch = {
        "validating_webhooks": (0, '{"items":[{"metadata":{"name":"policy"},"webhooks":[{"name":"policy.example","clientConfig":{"service":{"name":"policy","namespace":"ops"}},"failurePolicy":"Fail"}]}]}'),
        "mutating_webhooks": (0, '{"items":[]}'),
        "apiservices": (0, '{"items":[{"metadata":{"name":"v1beta1.metrics.k8s.io"},"status":{"conditions":[{"type":"Available","status":"False","reason":"FailedDiscoveryCheck"}]}}]}'),
        "crds": (0, '{"items":[{"metadata":{"name":"widgets.example.com"},"spec":{"versions":[{"name":"v1","served":true,"storage":true},{"name":"v1beta1","served":true,"storage":false}]}}]}'),
        "system_daemonsets": (0, '{"items":[{"metadata":{"name":"cni"},"status":{"desiredNumberScheduled":2,"numberReady":1}}]}'),
        "system_deployments": (0, '{"items":[]}'),
        "nodes": (0, '{"items":[{"metadata":{"name":"node-1"},"status":{"nodeInfo":{"kubeletVersion":"v1.35.7","osImage":"Ubuntu","containerRuntimeVersion":"containerd://2"},"conditions":[{"type":"Ready","status":"True"}]}}]}'),
    }
    monkeypatch.setattr(compatibility, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = compatibility.aks_check_upgrade_compatibility(*ARGS, target_kubernetes_version="1.35.7")

    assert result["status"] == "BLOCKED"
    assert result["unavailable_api_services"][0]["name"] == "v1beta1.metrics.k8s.io"
    assert result["webhooks"][0]["has_ca_bundle"] is False
    assert result["crds"][0]["storage_versions"] == ["v1"]
    assert result["node_summary"]["checked"] == 1
    assert result["nodes"] == []
    assert result["run_command_invocations"] == 1


def test_upgrade_compatibility_passes_clean_inventory(monkeypatch):
    empty_batch = {label: (0, '{"items":[]}') for label in (
        "validating_webhooks", "mutating_webhooks", "apiservices", "crds",
        "system_daemonsets", "system_deployments", "nodes",
    )}
    monkeypatch.setattr(compatibility, "run_kubectl_batch", lambda *_a, **_k: empty_batch)

    result = compatibility.aks_check_upgrade_compatibility(*ARGS)

    assert result["status"] == "PASS"
    assert result["blockers"] == []
    assert result["query_errors"] == []


def test_upgrade_compatibility_falls_back_for_malformed_batch_section(monkeypatch):
    batch = {
        "validating_webhooks": (0, '{"items":[]}'),
        "mutating_webhooks": (0, '{"items":[]}'),
        "apiservices": (0, '{"items":[]}'),
        "crds": (0, '{"items":[bad]}'),
        "system_daemonsets": (0, '{"items":[]}'),
        "system_deployments": (0, '{"items":[]}'),
        "nodes": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(compatibility, "run_kubectl_batch", lambda *_a, **_k: batch)
    monkeypatch.setattr(
        compatibility,
        "run_kubectl_json",
        lambda *_a, **_k: {"items": [{"metadata": {"name": "widgets.example.com"}, "spec": {"versions": []}}]},
    )

    result = compatibility.aks_check_upgrade_compatibility(*ARGS)

    assert result["query_errors"] == []
    assert result["crds"][0]["name"] == "widgets.example.com"


def test_upgrade_compatibility_marks_query_warning_as_incomplete(monkeypatch):
    empty_batch = {label: (0, '{"items":[]}') for label in (
        "validating_webhooks", "mutating_webhooks", "apiservices", "crds",
        "system_daemonsets", "system_deployments", "nodes",
    )}
    monkeypatch.setattr(compatibility, "run_kubectl_batch", lambda *_a, **_k: empty_batch)
    monkeypatch.setattr(
        compatibility,
        "run_kubectl_json",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("fallback failed")),
    )

    # Force one fallback parse failure while retaining a warning finding.
    malformed = dict(empty_batch)
    malformed["crds"] = (0, '{"items":[bad]}')
    monkeypatch.setattr(compatibility, "run_kubectl_batch", lambda *_a, **_k: malformed)

    result = compatibility.aks_check_upgrade_compatibility(*ARGS)

    assert result["query_errors"]
    assert result["status"] == "INCOMPLETE"

from __future__ import annotations

from tools import platform


ARGS = ("sub", "rg", "cluster")


def test_platform_addons_reports_csi_storage_helm_and_system_workloads(monkeypatch):
    batch = {
        "csidrivers": (0, '{"items":[{"metadata":{"name":"disk.csi.azure.com"},"spec":{"driver":"disk.csi.azure.com","attachRequired":true}}]}'),
        "csinodes": (0, '{"items":[{"metadata":{"name":"node-1"}}]}'),
        "storageclasses": (0, '{"items":[{"metadata":{"name":"managed-csi"},"provisioner":"disk.csi.azure.com","reclaimPolicy":"Delete","volumeBindingMode":"WaitForFirstConsumer"}]}'),
        "system_daemonsets": (0, '{"items":[{"kind":"DaemonSet","metadata":{"name":"cni","namespace":"kube-system"},"status":{"desiredNumberScheduled":2,"numberReady":2}}]}'),
        "system_deployments": (0, '{"items":[]}'),
        "operator_workloads": (0, '{"items":[{"kind":"Deployment","metadata":{"name":"operator","namespace":"ops"}}]}'),
    }
    monkeypatch.setattr(platform, "run_kubectl_batch", lambda *_a, **_k: batch)
    monkeypatch.setattr(platform, "run_kubectl_raw", lambda *_a, **_k: '[{"name":"phonebook","namespace":"default","chart":"phonebook-1.2.3"}]')

    result = platform.aks_check_platform_addons(*ARGS, target_kubernetes_version="1.35.7")

    assert result["status"] == "PASS"
    assert result["csi_drivers"][0]["name"] == "disk.csi.azure.com"
    assert result["storage_classes"][0]["provisioner"] == "disk.csi.azure.com"
    assert result["operator_workloads"][0]["name"] == "operator"
    assert result["helm"]["status"] == "REPORT"


def test_platform_addons_reports_query_errors(monkeypatch):
    monkeypatch.setattr(platform, "run_kubectl_batch", lambda *_a, **_k: {})
    monkeypatch.setattr(platform, "run_kubectl_raw", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("helm unavailable")))

    result = platform.aks_check_platform_addons(*ARGS)

    assert result["status"] == "INCOMPLETE"
    assert result["query_errors"]


def test_platform_addons_falls_back_for_large_system_workload_sections(monkeypatch):
    batch = {label: (0, '{"items":[]}') for label in (
        "csidrivers", "csinodes", "storageclasses", "system_daemonsets",
        "system_deployments", "operator_workloads",
    )}
    batch["system_daemonsets"] = (0, '{"items":[bad]}')
    monkeypatch.setattr(platform, "run_kubectl_batch", lambda *_a, **_k: batch)
    monkeypatch.setattr(
        platform,
        "run_kubectl_json",
        lambda *_a, **_k: {"items": [{"kind": "DaemonSet", "metadata": {"name": "cni"}, "status": {"desiredNumberScheduled": 1, "numberReady": 1}}]},
    )
    monkeypatch.setattr(platform, "run_kubectl_raw", lambda *_a, **_k: "[]")

    result = platform.aks_check_platform_addons(*ARGS)

    assert result["query_errors"] == []
    assert result["system_workloads"][0]["name"] == "cni"

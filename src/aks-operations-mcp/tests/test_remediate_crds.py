from __future__ import annotations

from tools import remediate_crds


ARGS = ("sub", "rg", "cluster")


def test_crd_planner_reports_ready_owner_review(monkeypatch):
    batch = {
        "crds": (0, '{"items":[{"metadata":{"name":"widgets.example.com"},"spec":{"group":"example.com","names":{"kind":"Widget","plural":"widgets"},"versions":[{"name":"v1","served":true,"storage":true}],"conversion":{"strategy":"None"}}}]}'),
        "apiservices": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(remediate_crds, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = remediate_crds.aks_plan_crd_conversion(*ARGS, crd_name="widgets.example.com", target_version="v1")

    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["storage_versions"] == ["v1"]
    assert result["writes_performed"] is False


def test_crd_planner_blocks_invalid_conversion_webhook(monkeypatch):
    batch = {
        "crds": (0, '{"items":[{"metadata":{"name":"widgets.example.com"},"spec":{"versions":[{"name":"v1","served":true,"storage":true},{"name":"v1beta1","served":true,"storage":false}],"conversion":{"strategy":"Webhook"}}}]}'),
        "apiservices": (0, '{"items":[]}'),
    }
    monkeypatch.setattr(remediate_crds, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = remediate_crds.aks_plan_crd_conversion(*ARGS, crd_name="widgets.example.com")

    assert result["status"] == "BLOCKED"
    assert result["blockers"]

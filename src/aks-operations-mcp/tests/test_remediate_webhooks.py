from __future__ import annotations

from tools import remediate_webhooks


ARGS = ("sub", "rg", "cluster")


def test_webhook_planner_returns_owner_review_plan(monkeypatch):
    batch = {
        "validating": (0, '{"items":[{"metadata":{"name":"policy"},"webhooks":[{"name":"policy.example","clientConfig":{"service":{"name":"policy","namespace":"ops"},"caBundle":"Y2E="},"failurePolicy":"Fail"}]}]}'),
        "mutating": (0, '{"items":[]}'),
        "services": (0, '{"items":[{"metadata":{"name":"policy","namespace":"ops"},"spec":{"clusterIP":"10.0.0.4","ports":[]}}]}'),
        "endpoints": (0, '{"items":[{"metadata":{"name":"policy","namespace":"ops"},"subsets":[{"addresses":[{"ip":"10.0.0.10"}]}]}]}'),
        "secrets": (0, '{"items":[{"metadata":{"name":"policy-tls","namespace":"ops"}}]}'),
    }
    monkeypatch.setattr(remediate_webhooks, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = remediate_webhooks.aks_plan_webhook_remediation(*ARGS, "policy", namespace="ops")

    assert result["status"] == "READY_FOR_OWNER_REVIEW"
    assert result["writes_performed"] is False
    assert result["endpoints"][0]["subsets"]


def test_webhook_planner_blocks_missing_ca_bundle(monkeypatch):
    empty = '{"items":[]}'
    batch = {label: (0, empty) for label in ("mutating", "services", "endpoints", "secrets")}
    batch["validating"] = (0, '{"items":[{"metadata":{"name":"policy"},"webhooks":[{"name":"policy.example","clientConfig":{}}]}]}')
    monkeypatch.setattr(remediate_webhooks, "run_kubectl_batch", lambda *_a, **_k: batch)

    result = remediate_webhooks.aks_plan_webhook_remediation(*ARGS, "policy")

    assert result["status"] == "BLOCKED"
    assert result["blockers"]

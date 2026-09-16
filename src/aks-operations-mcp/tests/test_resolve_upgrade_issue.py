from __future__ import annotations

from tools.resolve_upgrade_issue import aks_resolve_upgrade_issue


def test_resolver_recommends_pdb_checks_for_disruption_issue() -> None:
    result = aks_resolve_upgrade_issue(
        issue="Node drain is blocked by a PDB",
        subscription_id="sub",
        resource_group="rg",
        cluster_name="cluster",
        target_version="1.35",
    )

    assert result["target_version"] == "1.35"
    assert result["recommended_checks"] == [
        {"category": "pdb", "recommended_tool": "aks_check_pdb"},
        {"category": "node", "recommended_tool": "aks_check_node_health"},
    ]
    assert result["dynamic_cli_available"] is True
    assert "approval_token" not in result["write_policy"]


def test_resolver_recommends_multiple_checks_for_mixed_issue() -> None:
    result = aks_resolve_upgrade_issue(
        issue="Pending pod because of storage and node capacity",
        subscription_id="sub",
        resource_group="rg",
        cluster_name="cluster",
    )

    categories = {item["category"] for item in result["recommended_checks"]}
    assert {"pods", "storage", "node"} <= categories


def test_resolver_classifies_automatable_remediation_capabilities() -> None:
    result = aks_resolve_upgrade_issue(
        issue="CrashLoopBackOff pod and PDB blocks node drain",
        subscription_id="sub",
        resource_group="rg",
        cluster_name="cluster",
    )

    capabilities = {item["category"]: item for item in result["remediation_capabilities"]}
    assert capabilities["pods"]["status"] == "AUTOMATABLE"
    assert "aks_remediate_pods" in capabilities["pods"]["tools"]
    assert capabilities["pdb"]["status"] == "AUTOMATABLE"
    assert "aks_remediate_pdb" in capabilities["pdb"]["tools"]


def test_resolver_classifies_operator_guided_migrations() -> None:
    result = aks_resolve_upgrade_issue(
        issue="Webhook certificate, CSI compatibility, CRD conversion, and backups need review",
        subscription_id="sub",
        resource_group="rg",
        cluster_name="cluster",
    )

    capabilities = {item["category"]: item for item in result["remediation_capabilities"]}
    assert capabilities["webhook"]["status"] == "OPERATOR_GUIDED"
    assert capabilities["addon"]["status"] == "OPERATOR_GUIDED"
    assert capabilities["crd"]["status"] == "OPERATOR_GUIDED"
    assert capabilities["backup"]["status"] == "OPERATOR_GUIDED"
    assert result["remediation_policy"]["operator_guided"].startswith("Do not infer")


def test_resolver_classifies_rwo_rwx_migration_as_operator_guided() -> None:
    result = aks_resolve_upgrade_issue(
        issue="Multi-Attach requires RWO to RWX storage migration",
        subscription_id="sub",
        resource_group="rg",
        cluster_name="cluster",
    )

    capabilities = {item["category"]: item for item in result["remediation_capabilities"]}
    assert capabilities["storage_migration"]["status"] == "OPERATOR_GUIDED"
    assert "aks_remediate_storage" not in capabilities["storage_migration"]["tools"]

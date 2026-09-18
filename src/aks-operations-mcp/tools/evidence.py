"""Structured evidence records and deterministic validity checks for assessments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def evidence_record(
    *,
    check_type: str,
    cluster_name: str,
    cluster_version: str | None,
    source_tool: str,
    scope: str,
    status: str,
    last_verified_at: str | None = None,
    valid_until: str | None = None,
    invalidation_conditions: list[str] | None = None,
    result: dict[str, Any] | None = None,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    verified_at = last_verified_at or datetime.now(UTC).isoformat()
    return {
        "evidence_id": evidence_id or f"EV-{uuid4().hex[:12]}",
        "check_type": check_type,
        "cluster_name": cluster_name,
        "cluster_version": cluster_version,
        "timestamp": verified_at,
        "source_tool": source_tool,
        "scope": scope,
        "status": status,
        "last_verified_at": verified_at,
        "valid_until": valid_until,
        "invalidation_conditions": invalidation_conditions or [
            "cluster_version_changed",
            "remediation_performed",
            "upgrade_executed",
            "relevant_configuration_changed",
            "assessment_scope_changed",
            "evidence_expired",
        ],
        "result": result or {},
    }


def validate_prior_evidence(
    evidence: dict[str, Any],
    *,
    cluster_name: str,
    cluster_version: str | None,
    scope: str,
    now: datetime | None = None,
    remediation_performed: bool = False,
    upgrade_performed: bool = False,
    configuration_changed: bool = False,
) -> tuple[bool, str]:
    if evidence.get("cluster_name") != cluster_name:
        return False, "cluster_name_changed"
    if evidence.get("scope") != scope:
        return False, "assessment_scope_changed"
    if evidence.get("status") not in {"PASS", "READY", "WARNING"}:
        return False, "prior_evidence_not_successful"
    recorded_version = evidence.get("cluster_version")
    if recorded_version and cluster_version and recorded_version != cluster_version:
        return False, "cluster_version_changed"
    if remediation_performed:
        return False, "remediation_performed"
    if upgrade_performed:
        return False, "upgrade_executed"
    if configuration_changed:
        return False, "relevant_configuration_changed"

    valid_until = evidence.get("valid_until")
    if valid_until:
        try:
            expiry = datetime.fromisoformat(valid_until.replace("Z", "+00:00"))
        except ValueError:
            return False, "evidence_expired"
        if expiry <= (now or datetime.now(UTC)):
            return False, "evidence_expired"
    return True, "validity_conditions_satisfied"
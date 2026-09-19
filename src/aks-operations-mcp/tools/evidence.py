"""Current-run evidence records for readiness assessments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def evidence_record(
    *,
    check_type: str,
    cluster_name: str,
    source_tool: str,
    scope: str,
    status: str,
    result: dict[str, Any],
    cluster_version: str | None = None,
) -> dict[str, Any]:
    """Create a new evidence record for the current assessment invocation."""
    verified_at = datetime.now(UTC).isoformat()
    return {
        "evidence_id": f"EV-{uuid4().hex[:12]}",
        "check_type": check_type,
        "cluster_name": cluster_name,
        "cluster_version": cluster_version,
        "timestamp": verified_at,
        "source_tool": source_tool,
        "scope": scope,
        "status": status,
        "last_verified_at": verified_at,
        "result": result,
    }

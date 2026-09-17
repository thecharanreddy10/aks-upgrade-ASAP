"""Single source of truth for the tools this server exposes.

Both entrypoints build their tool tables from ALL_TOOLS - the FastMCP server in main.py and
the Azure Functions JSON-RPC surface in function_app.py - so the two can no longer drift apart
as tools are added.
"""

from __future__ import annotations

import inspect
import json
import logging
from functools import wraps
from typing import Any, Callable, get_args, get_origin, get_type_hints

from tools.cli_operations import aks_az_read, aks_az_write, aks_kubectl_read, aks_kubectl_write
from tools.compatibility import aks_check_upgrade_compatibility
from tools.deprecated_apis import aks_check_deprecated_apis
from tools.discovery import (
    aks_get_available_upgrades,
    aks_get_cluster_details,
    aks_get_node_pools,
)
from tools.remediate_deprecated_apis import (
    aks_generate_deprecated_api_manifests,
    aks_remediate_deprecated_apis,
)
from tools.remediate_crds import aks_plan_crd_conversion
from tools.remediate_nodes import aks_remediate_node
from tools.remediate_pdb import aks_remediate_pdb, aks_rollback_pdb_remediation
from tools.remediate_pods import aks_remediate_pods
from tools.remediate_storage import aks_remediate_storage
from tools.remediate_webhooks import aks_plan_webhook_remediation
from tools.platform import aks_check_platform_addons
from tools.remediate_platform import aks_plan_platform_addon_remediation
from tools.rbac import aks_check_rbac_api_health
from tools.remediate_rbac import aks_apply_rbac_remediation, aks_plan_rbac_remediation, aks_rollback_rbac_remediation
from tools.resolve_upgrade_issue import aks_plan_upgrade_issue_remediation, aks_resolve_upgrade_issue
from tools.storage import aks_check_storage
from tools.async_upgrade import aks_execute_confirmed_upgrade
from tools.upgrade import (
    aks_collect_pre_upgrade_inventory,
    aks_get_upgrade_execution_status,
    aks_plan_upgrade_preparation,
    aks_run_post_upgrade_smoke_checks,
    aks_stage_result_summary,
    aks_upgrade_node_pool,
    aks_validate_upgrade_readiness,
)
from tools.validation import (
    aks_check_node_health,
    aks_check_operator_health,
    aks_check_pdb,
    aks_check_pod_health,
    aks_check_priority_class,
    aks_check_service_ingress_urls,
    aks_check_single_replica_services,
    aks_check_node_pool_surge,
)

logger = logging.getLogger(__name__)

_REGISTERED_TOOLS: tuple[Callable[..., dict[str, Any]], ...] = (
    aks_get_cluster_details,
    aks_get_node_pools,
    aks_get_available_upgrades,
    aks_collect_pre_upgrade_inventory,
    aks_stage_result_summary,
    aks_check_node_health,
    aks_check_pod_health,
    aks_check_pdb,
    aks_check_storage,
    aks_check_upgrade_compatibility,
    aks_check_platform_addons,
    aks_plan_platform_addon_remediation,
    aks_check_rbac_api_health,
    aks_plan_rbac_remediation,
    aks_apply_rbac_remediation,
    aks_rollback_rbac_remediation,
    aks_check_deprecated_apis,
    aks_validate_upgrade_readiness,
    aks_plan_upgrade_preparation,
    aks_execute_confirmed_upgrade,
    aks_get_upgrade_execution_status,
    aks_run_post_upgrade_smoke_checks,
    aks_upgrade_node_pool,
    aks_remediate_pdb,
    aks_rollback_pdb_remediation,
    aks_remediate_pods,
    aks_remediate_node,
    aks_remediate_storage,
    aks_plan_webhook_remediation,
    aks_remediate_deprecated_apis,
    aks_generate_deprecated_api_manifests,
    aks_plan_crd_conversion,
    aks_kubectl_read,
    aks_kubectl_write,
    aks_az_read,
    aks_az_write,
    aks_resolve_upgrade_issue,
    aks_plan_upgrade_issue_remediation,
    aks_check_single_replica_services,
    aks_check_operator_health,
    aks_check_node_pool_surge,
    aks_check_priority_class,
    aks_check_service_ingress_urls,
)


def _instrument_tool(tool: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Log bounded result metadata without logging the result body."""
    @wraps(tool)
    def instrumented(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = tool(*args, **kwargs)
        try:
            serialized = json.dumps(result, separators=(",", ":"), default=str)
            result_chars = len(serialized)
            result_bytes = len(serialized.encode("utf-8"))
        except (TypeError, ValueError):
            result_chars = 0
            result_bytes = 0

        truncated = bool(
            isinstance(result, dict)
            and any(result.get(key) for key in ("output_truncated", "details_truncated", "truncated"))
        )
        status = result.get("status") if isinstance(result, dict) else None
        logger.info(
            "tool_result tool=%s result_chars=%d result_bytes=%d estimated_tokens=%d status=%s truncated=%s",
            tool.__name__,
            result_chars,
            result_bytes,
            max(1, result_chars // 4) if result_chars else 0,
            status or "unset",
            truncated,
        )
        return result

    return instrumented


ALL_TOOLS: tuple[Callable[..., dict[str, Any]], ...] = tuple(
    _instrument_tool(tool) for tool in _REGISTERED_TOOLS
)

logger.info("mcp_tool_baseline registered_tools=%d", len(ALL_TOOLS))

_JSON_TYPES: dict[Any, str] = {str: "string", int: "integer", float: "number", bool: "boolean"}


def _schema_for_annotation(annotation: Any) -> dict[str, Any]:
    """Map a Python annotation onto a minimal JSON Schema fragment."""
    union_args = get_args(annotation)
    if union_args:
        nullable = type(None) in union_args
        list_args = [arg for arg in union_args if get_origin(arg) is list]
        if nullable and len(list_args) == 1:
            item_args = get_args(list_args[0])
            item_schema = _schema_for_annotation(item_args[0]) if item_args else {}
            return {"anyOf": [{"type": "array", "items": item_schema}, {"type": "null"}]}
        names = sorted({_JSON_TYPES[arg] for arg in union_args if arg in _JSON_TYPES})
        if not names:
            return {}
        return {"type": [*names, "null"] if nullable else (names[0] if len(names) == 1 else names)}

    if get_origin(annotation) is list:
        item_args = get_args(annotation)
        item_schema = _schema_for_annotation(item_args[0]) if item_args else {}
        return {"type": "array", "items": item_schema}

    mapped = _JSON_TYPES.get(annotation)
    return {"type": mapped} if mapped else {}


def build_input_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Derive a JSON Schema for a tool from its signature, so schemas can't fall out of sync."""
    hints = get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for name, param in inspect.signature(func).parameters.items():
        properties[name] = _schema_for_annotation(hints.get(name))
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {"type": "object", "properties": properties, "required": required}


def tool_description(func: Callable[..., Any]) -> str:
    """First line of the tool's docstring, used as its advertised description."""
    doc = inspect.getdoc(func) or ""
    return doc.split("\n", 1)[0] or f"AKS operation: {func.__name__}"
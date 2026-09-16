"""Read-only CRD conversion and version migration planning."""

from __future__ import annotations

import json
from typing import Any

from tools.common import run_kubectl_batch, validate_k8s_name


def _items(batch: dict[str, tuple[int, str]], label: str) -> list[dict[str, Any]]:
    exit_code, raw = batch.get(label, (1, ""))
    if exit_code != 0 or not raw.strip():
        return []
    try:
        return json.loads(raw, strict=False).get("items", [])
    except json.JSONDecodeError:
        return []


def aks_plan_crd_conversion(
    subscription_id: str,
    resource_group: str,
    cluster_name: str,
    crd_name: str,
    target_version: str | None = None,
) -> dict[str, Any]:
    """Inspect a CRD and its custom resources and return a no-write conversion plan."""
    validate_k8s_name(crd_name, "custom resource definition")
    batch = run_kubectl_batch(
        subscription_id,
        resource_group,
        cluster_name,
        {
            "crds": "get crd",
            "apiservices": "get apiservice",
        },
    )
    crds = [item for item in _items(batch, "crds") if item.get("metadata", {}).get("name") == crd_name]
    if not crds:
        return {
            "status": "NOT_FOUND",
            "crd_name": crd_name,
            "writes_performed": False,
            "message": "CRD was not found.",
        }

    crd = crds[0]
    spec = crd.get("spec", {}) or {}
    versions = spec.get("versions", []) or []
    conversion = spec.get("conversion", {}) or {}
    served = [version.get("name") for version in versions if version.get("served")]
    storage = [version.get("name") for version in versions if version.get("storage")]
    webhook = conversion.get("webhook", {}) or {}
    client_config = webhook.get("clientConfig", {}) or {}
    service = client_config.get("service", {}) or {}

    warnings: list[str] = []
    blockers: list[str] = []
    if len(storage) != 1:
        blockers.append(f"CRD has {len(storage)} storage versions; exactly one storage version is required.")
    if len(served) > 1 and conversion.get("strategy", "None") == "None":
        blockers.append("CRD serves multiple versions without a conversion strategy.")
    if conversion.get("strategy") == "Webhook" and not service.get("name") and not client_config.get("url"):
        blockers.append("CRD uses webhook conversion but has no service or URL reference.")
    if target_version and target_version not in served:
        warnings.append(f"Requested CRD version {target_version} is not currently served.")
    if conversion.get("strategy") == "Webhook" and not client_config.get("caBundle"):
        warnings.append("CRD conversion webhook has no embedded CA bundle; verify certificate trust separately.")

    status = "BLOCKED" if blockers else ("WARNING" if warnings else "READY_FOR_OWNER_REVIEW")
    return {
        "status": status,
        "crd_name": crd_name,
        "target_version": target_version,
        "served_versions": served,
        "storage_versions": storage,
        "conversion_strategy": conversion.get("strategy", "None"),
        "conversion_webhook": {
            "service": service,
            "url": client_config.get("url"),
            "has_ca_bundle": bool(client_config.get("caBundle")),
        },
        "custom_resource_inventory": {
            "group": spec.get("group"),
            "kind": spec.get("names", {}).get("kind"),
            "plural": spec.get("names", {}).get("plural"),
            "read_required": True,
        },
        "blockers": blockers,
        "warnings": warnings,
        "writes_performed": False,
        "plan": [
            "Back up or export existing custom resources before changing CRD schemas.",
            "Update the CRD and owning operator together, preserving one storage version and explicit conversion behavior.",
            "Test conversion of existing custom resources with server-side dry-run in a safe environment.",
            "Apply the migration only after explicit authorization, then verify served/storage versions and operator health.",
        ],
        "required_authorization": "A separate explicit approval is required for CRD, operator, or custom-resource migration.",
    }

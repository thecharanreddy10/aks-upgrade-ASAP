"""Non-sensitive per-model-call context diagnostics for temporary investigations."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from agent_framework import ChatContext, ChatMiddleware, ChatResponse, ResponseStream

logger = logging.getLogger(__name__)


def _json_size(value: Any) -> tuple[int, int]:
    try:
        serialized = json.dumps(value, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        serialized = str(value)
    return len(serialized), len(serialized.encode("utf-8"))


def _content_size(content: Any) -> int:
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return len(text)
    for attribute in ("arguments", "result"):
        value = getattr(content, attribute, None)
        if value is not None:
            return _json_size(value)[0]
    return _json_size({"type": getattr(content, "type", type(content).__name__)} )[0]


def _message_size(message: Any) -> int:
    contents = getattr(message, "contents", None) or []
    return sum(_content_size(content) for content in contents)


def _role(message: Any) -> str:
    role = getattr(message, "role", "")
    return getattr(role, "value", role) or "unknown"


def _message_metrics(messages: Sequence[Any]) -> dict[str, int]:
    metrics = {
        "system_chars": 0,
        "history_chars": 0,
        "current_input_chars": 0,
        "tool_call_chars": 0,
        "tool_result_chars": 0,
        "message_count": len(messages),
    }
    last_user_index = max(
        (index for index, message in enumerate(messages) if _role(message) == "user"),
        default=-1,
    )
    for index, message in enumerate(messages):
        size = _message_size(message)
        role = _role(message)
        content_types = {
            getattr(content, "type", "")
            for content in (getattr(message, "contents", None) or [])
        }
        if role in {"system", "developer"}:
            metrics["system_chars"] += size
        elif "function_call" in content_types:
            metrics["tool_call_chars"] += size
        elif "function_result" in content_types:
            metrics["tool_result_chars"] += size
        elif index == last_user_index:
            metrics["current_input_chars"] += size
        elif index < last_user_index or last_user_index < 0:
            metrics["history_chars"] += size
    return metrics


def _instruction_chars(options: Mapping[str, Any] | None) -> int:
    instructions = (options or {}).get("instructions")
    if instructions is None:
        return 0
    return _json_size(instructions)[0]


def _tool_metrics(options: Mapping[str, Any] | None) -> tuple[int, int, list[dict[str, Any]]]:
    tools = list((options or {}).get("tools") or [])
    entries: list[dict[str, Any]] = []
    for tool in tools:
        name = getattr(tool, "name", None) or getattr(tool, "server_label", None) or type(tool).__name__
        description = getattr(tool, "description", None)
        shape: dict[str, Any] = {"name": str(name)}
        if description:
            shape["description"] = str(description)
        to_dict = getattr(tool, "to_dict", None)
        if callable(to_dict):
            try:
                shape = to_dict()
            except Exception:  # noqa: BLE001
                pass
        chars, _ = _json_size(shape)
        entries.append({"name": str(name), "chars": chars})
    total_chars = sum(entry["chars"] for entry in entries)
    total_bytes = _json_size(entries)[1]
    entries.sort(key=lambda entry: entry["chars"], reverse=True)
    return total_chars, total_bytes, entries[:10]


def _usage(response: Any) -> dict[str, int | None]:
    details = getattr(response, "usage_details", None) or {}
    return {
        "input_tokens": details.get("input_token_count"),
        "cached_input_tokens": details.get("cache_read_input_token_count"),
        "cache_creation_input_tokens": details.get("cache_creation_input_token_count"),
        "output_tokens": details.get("output_token_count"),
        "reasoning_output_tokens": details.get("reasoning_output_token_count"),
        "total_tokens": details.get("total_token_count"),
    }


def _log_result(call_id: str, deployment: str, metrics: dict[str, Any], response: Any) -> Any:
    usage = _usage(response)
    logger.info(
        "model_context_result call_id=%s timestamp=%s deployment=%s "
        "system_chars=%s history_chars=%s current_input_chars=%s tool_call_chars=%s tool_result_chars=%s "
        "message_count=%s estimated_context_tokens=%s input_tokens=%s cached_input_tokens=%s "
        "output_tokens=%s total_tokens=%s reasoning_output_tokens=%s",
        call_id,
        datetime.now(timezone.utc).isoformat(),
        deployment,
        metrics["system_chars"],
        metrics["history_chars"],
        metrics["current_input_chars"],
        metrics["tool_call_chars"],
        metrics["tool_result_chars"],
        metrics["message_count"],
        max(1, metrics["estimated_context_chars"] // 4),
        usage["input_tokens"],
        usage["cached_input_tokens"],
        usage["output_tokens"],
        usage["total_tokens"],
        usage["reasoning_output_tokens"],
    )
    return response


class ContextDiagnosticsMiddleware(ChatMiddleware):
    """Report model-call sizes and usage without recording message contents."""

    async def process(
        self,
        context: ChatContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        call_id = uuid.uuid4().hex
        try:
            message_metrics = _message_metrics(list(context.messages))
            message_metrics["system_chars"] += _instruction_chars(context.options)
            tool_chars, tool_bytes, largest_tools = _tool_metrics(context.options)
            message_metrics["estimated_context_chars"] = (
                sum(value for key, value in message_metrics.items() if key.endswith("_chars"))
                + tool_chars
            )
            deployment = str((context.options or {}).get("model") or type(context.client).__name__)
            logger.info(
                "model_context_call call_id=%s timestamp=%s deployment=%s stream=%s "
                "message_count=%s system_chars=%s history_chars=%s current_input_chars=%s "
                "tool_call_chars=%s tool_result_chars=%s tool_count=%s tool_definition_chars=%s "
                "tool_definition_bytes=%s estimated_context_tokens=%s largest_tools=%s",
                call_id,
                datetime.now(timezone.utc).isoformat(),
                deployment,
                context.stream,
                message_metrics["message_count"],
                message_metrics["system_chars"],
                message_metrics["history_chars"],
                message_metrics["current_input_chars"],
                message_metrics["tool_call_chars"],
                message_metrics["tool_result_chars"],
                len((context.options or {}).get("tools") or []),
                tool_chars,
                tool_bytes,
                max(1, message_metrics["estimated_context_chars"] // 4),
                largest_tools,
            )
            await call_next()
            result = context.result
            if isinstance(result, ResponseStream):
                result.with_result_hook(
                    lambda response: _log_result(call_id, deployment, message_metrics, response)
                )
            elif isinstance(result, ChatResponse):
                _log_result(call_id, deployment, message_metrics, result)
        except Exception:  # noqa: BLE001
            logger.exception("model_context_diagnostics_failed call_id=%s", call_id)
            # Diagnostics must never change model-call behavior.

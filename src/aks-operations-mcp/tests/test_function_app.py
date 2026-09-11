import json

import azure.functions as func

import function_app


def _post(payload: dict) -> func.HttpRequest:
    return func.HttpRequest(
        method="POST",
        url="/api/mcp",
        body=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def test_tool_exception_returns_jsonrpc_error_without_http_failure(monkeypatch):
    def failing_tool() -> dict:
        raise RuntimeError("boom")

    monkeypatch.setitem(function_app.TOOLS, "failing_tool", failing_tool)

    response = function_app.mcp(
        _post({"jsonrpc": "2.0", "id": "1", "method": "tools/call", "params": {"name": "failing_tool", "arguments": {}}})
    )
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload == {
        "jsonrpc": "2.0",
        "id": "1",
        "error": {"code": -32000, "message": "boom"},
    }


def test_invalid_tool_arguments_return_jsonrpc_error_without_http_failure(monkeypatch):
    def required_arg_tool(name: str) -> dict:
        return {"name": name}

    monkeypatch.setitem(function_app.TOOLS, "required_arg_tool", required_arg_tool)

    response = function_app.mcp(
        _post({"jsonrpc": "2.0", "id": "1", "method": "tools/call", "params": {"name": "required_arg_tool", "arguments": {}}})
    )
    payload = json.loads(response.get_body().decode("utf-8"))

    assert response.status_code == 200
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == "1"
    assert payload["error"]["code"] == -32602
    assert "Invalid arguments" in payload["error"]["message"]
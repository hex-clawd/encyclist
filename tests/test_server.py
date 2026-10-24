"""Server-level smoke tests: ASGI app boots, /health responds, MCP
endpoint enforces the API-key middleware.

Each test function gets its OWN app + client to avoid StreamableHTTPSessionManager
reuse issues (it can only .run() once per instance).
"""

from __future__ import annotations

import httpx
import pytest


async def _make_client_and_app(server_env):
    """Helper: build a fresh app + client pair with its own lifespan."""
    from src import server as srv

    if hasattr(srv.mcp, "_session_manager"):
        srv.mcp._session_manager = None
    app = srv.build_app()
    inner = app.app  # APIKeyMiddleware -> Starlette
    # Enter lifespan manually
    cm = inner.router.lifespan_context(inner)
    await cm.__aenter__()
    transport = httpx.ASGITransport(app=app)
    c = httpx.AsyncClient(transport=transport, base_url="http://localhost")
    return c, cm


@pytest.mark.asyncio
async def test_health_no_auth_required(server_env):
    client, cm = await _make_client_and_app(server_env)
    try:
        resp = await client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "encyclist"
    finally:
        await client.aclose()
        await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_mcp_requires_api_key(server_env):
    client, cm = await _make_client_and_app(server_env)
    try:
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "unauthorized"
    finally:
        await client.aclose()
        await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_mcp_accepts_valid_api_key(server_env):
    client, cm = await _make_client_and_app(server_env)
    try:
        _, keys = server_env
        key = keys[0]["key"]
        resp = await client.post(
            "/mcp",
            headers={
                "X-API-Key": key,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert resp.status_code != 401
        assert resp.status_code in (200, 202)
    finally:
        await client.aclose()
        await cm.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_mcp_lists_all_tools(server_env):
    client, cm = await _make_client_and_app(server_env)
    try:
        _, keys = server_env
        key = keys[0]["key"]
        headers = {
            "X-API-Key": key,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }

        init = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "0"},
                },
            },
        )
        assert init.status_code == 200

        # Session ID may come as header or inside SSE body
        session_id = init.headers.get("mcp-session-id")

        # `notifications/initialized` per protocol
        notif_headers = dict(headers)
        if session_id:
            notif_headers["mcp-session-id"] = session_id
        await client.post(
            "/mcp",
            headers=notif_headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )

        list_headers = dict(headers)
        if session_id:
            list_headers["mcp-session-id"] = session_id
        listing = await client.post(
            "/mcp",
            headers=list_headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        assert listing.status_code == 200
        body = _parse_sse_or_json(listing)
        tool_names = {t["name"] for t in body["result"]["tools"]}

        expected = {
            "ec_doc_add", "ec_doc_search", "ec_doc_get", "ec_doc_update",
            "ec_doc_list", "ec_doc_delete",
            "ec_entity_type_define", "ec_entity_type_list",
            "ec_entity_create", "ec_entity_get", "ec_entity_query",
            "ec_entity_update", "ec_entity_delete",
            "ec_rel_add", "ec_rel_query", "ec_rel_delete",
            "ec_stats", "ec_search", "ec_export", "ec_import",
            "ec_key_create", "ec_key_list", "ec_key_revoke",
        }
        missing = expected - tool_names
        assert not missing, f"missing MCP tools: {missing}"
    finally:
        await client.aclose()
        await cm.__aexit__(None, None, None)


def _parse_sse_or_json(resp: httpx.Response) -> dict:
    """MCP responses come back as SSE when negotiated; pick out the
    first `data:` payload and parse it as JSON-RPC."""
    import json

    ctype = resp.headers.get("content-type", "")
    if "text/event-stream" in ctype:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[len("data:"):].strip())
        raise AssertionError(f"no data: payload in SSE body:\n{resp.text}")
    return resp.json()

"""Thin MCP client wrapper around `streamablehttp_client`.

A fresh client session is opened per tool call. The remote Encyclist
server runs in `stateless_http=True` mode, so there is no session
state to preserve between calls — each request is independent and the
short-lived session keeps the code simple and reconnect-free.

The `call_tool` coroutine handles result decoding: FastMCP returns the
tool's Python value as JSON-encoded TextContent, so we parse the first
text block back into a Python object. Tool errors raise `MCPToolError`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


class MCPToolError(RuntimeError):
    """Raised when a remote MCP tool call fails."""


class MCPConfigError(RuntimeError):
    """Raised when the client is missing required configuration."""


def _config() -> tuple[str, str]:
    url = os.environ.get("ENCYCLIST_URL", "").strip()
    key = os.environ.get("ENCYCLIST_API_KEY", "").strip()
    if not url:
        raise MCPConfigError(
            "ENCYCLIST_URL is not set. Copy .env.example to .env and fill it in."
        )
    if not key:
        raise MCPConfigError(
            "ENCYCLIST_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return url, key


def _decode_result(result: Any) -> Any:
    """Convert a CallToolResult into a plain Python value.

    Order of preference: structuredContent (if present and meaningful),
    then JSON-decoded TextContent, then the raw text. Lists wrapped in
    `{"result": [...]}` by FastMCP for schema reasons are unwrapped.
    """
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict) and set(structured.keys()) == {"result"}:
        return structured["result"]
    if structured is not None:
        return structured

    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text is None:
            continue
        try:
            return json.loads(text)
        except (TypeError, ValueError):
            return text
    return None


async def call_tool(name: str, arguments: Optional[dict] = None) -> Any:
    """Call a remote MCP tool by name and return the decoded result."""
    url, api_key = _config()
    headers = {"X-API-Key": api_key}

    async with streamablehttp_client(url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments or {})
            if getattr(result, "isError", False):
                # Pull whatever error text the server sent.
                msg = ""
                for block in getattr(result, "content", []) or []:
                    msg += getattr(block, "text", "") or ""
                raise MCPToolError(msg or f"Tool {name!r} returned an error")
            return _decode_result(result)


async def safe_call(name: str, arguments: Optional[dict] = None, default: Any = None) -> Any:
    """Like `call_tool` but swallows errors and returns `default` instead.

    Useful for sidebar/optional sections where a partial failure
    shouldn't break the whole page.
    """
    try:
        return await call_tool(name, arguments)
    except Exception:
        return default

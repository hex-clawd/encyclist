"""Encyclist MCP server (StreamableHTTP transport).

Boot flow:
1. Load config (`ENCYCLIST_DATA_DIR`, `ENCYCLIST_KEYS`).
2. Open SQLite, init schema, sync API keys from env.
3. Open ChromaDB persistent client.
4. Register MCP tools on a FastMCP instance.
5. Compose ASGI: API-key middleware → routes (`/health`, `/mcp`).

Auth lives in middleware so a single check guards every MCP request;
the validated key's `name` is stashed in a contextvar that tools read
when stamping `created_by` / audit-log entries.
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from src.auth import APIKeyAuth, current_api_key_name
from src.config import Config, load_config
from src.db import connect, init_schema
from src.doc_store import DocStore
from src.entity_store import EntityStore
from src.graph import Graph

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------


def _build_components(config: Config):
    conn = connect(config.db_path)
    init_schema(conn)
    auth = APIKeyAuth(conn)
    auth.sync_from_env(config.keys)
    entities = EntityStore(conn)
    docs = DocStore(conn, config.chroma_dir)
    graph = Graph(conn)
    return conn, auth, entities, docs, graph


CONFIG = load_config()
CONN, AUTH, ENTITIES, DOCS, GRAPH = _build_components(CONFIG)


def _author() -> Optional[str]:
    """Name of the API key behind the current request (or None in tests)."""
    return current_api_key_name.get()


# ---------------------------------------------------------------------------
# MCP server + tool definitions
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "encyclist",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)


# ---- Document store ------------------------------------------------------

@mcp.tool()
def ec_doc_add(
    content: str,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
    source: Optional[str] = None,
) -> dict:
    """Store a document. Content is indexed by meaning automatically."""
    result = DOCS.add(content=content, title=title, tags=tags, source=source)
    ENTITIES.log_change("create", "doc", result["doc_id"], {"title": title}, _author())
    return result


@mcp.tool()
def ec_doc_search(
    query: str,
    tags: Optional[list[str]] = None,
    source: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """Semantic search across documents. Finds by meaning, not keywords."""
    return DOCS.search(query=query, tags=tags, source=source, limit=limit)


@mcp.tool()
def ec_doc_get(doc_id: str) -> dict:
    """Retrieve a specific document by ID."""
    doc = DOCS.get(doc_id)
    if doc is None:
        raise ValueError(f"Document not found: {doc_id!r}")
    return doc


@mcp.tool()
def ec_doc_update(
    doc_id: str,
    content: Optional[str] = None,
    title: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Update an existing document's content or metadata."""
    result = DOCS.update(doc_id=doc_id, content=content, title=title, tags=tags)
    ENTITIES.log_change(
        "update", "doc", doc_id,
        {"content_changed": content is not None, "title": title, "tags": tags},
        _author(),
    )
    return result


@mcp.tool()
def ec_doc_list(
    tags: Optional[list[str]] = None,
    source: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List documents, optionally filtered by tags or source."""
    return DOCS.list(tags=tags, source=source, limit=limit, offset=offset)


@mcp.tool()
def ec_doc_delete(doc_id: str) -> dict:
    """Remove a document."""
    if not DOCS.delete(doc_id):
        raise ValueError(f"Document not found: {doc_id!r}")
    ENTITIES.log_change("delete", "doc", doc_id, None, _author())
    return {"status": "deleted", "doc_id": doc_id}


# ---- Entity types --------------------------------------------------------

@mcp.tool()
def ec_entity_type_define(
    name: str,
    fields: dict,
    description: Optional[str] = None,
) -> dict:
    """Define a new entity type with its field schema."""
    result = ENTITIES.define_type(name=name, fields=fields, description=description)
    ENTITIES.log_change(
        "create", "entity_type", name,
        {"fields": list(fields.keys()), "description": description},
        _author(),
    )
    return result


@mcp.tool()
def ec_entity_type_list() -> list[dict]:
    """List all defined entity types."""
    return ENTITIES.list_types()


# ---- Entities ------------------------------------------------------------

@mcp.tool()
def ec_entity_create(type: str, data: dict) -> dict:  # noqa: A002 - matches MCP spec
    """Create a new entity instance."""
    result = ENTITIES.create_entity(type_name=type, data=data, created_by=_author())
    ENTITIES.log_change(
        "create", "entity", result["entity_id"], {"type": type}, _author()
    )
    return result


@mcp.tool()
def ec_entity_get(entity_id: str) -> dict:
    """Get a single entity by ID."""
    entity = ENTITIES.get_entity(entity_id)
    if entity is None:
        raise ValueError(f"Entity not found: {entity_id!r}")
    return entity


@mcp.tool()
def ec_entity_query(
    type: str,  # noqa: A002 - matches MCP spec
    where: Optional[dict] = None,
    order_by: Optional[str] = None,
    order_dir: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Exact structured query over entities of a given type."""
    return ENTITIES.query_entities(
        type_name=type,
        where=where,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )


@mcp.tool()
def ec_entity_update(entity_id: str, data: dict) -> dict:
    """Partial update — only listed fields change."""
    result = ENTITIES.update_entity(entity_id=entity_id, data=data)
    ENTITIES.log_change(
        "update", "entity", entity_id, {"fields": list(data.keys())}, _author()
    )
    return result


@mcp.tool()
def ec_entity_delete(entity_id: str) -> dict:
    """Delete an entity."""
    if not ENTITIES.delete_entity(entity_id):
        raise ValueError(f"Entity not found: {entity_id!r}")
    ENTITIES.log_change("delete", "entity", entity_id, None, _author())
    return {"status": "deleted", "entity_id": entity_id}


# ---- Relationships -------------------------------------------------------

@mcp.tool()
def ec_rel_add(
    from_id: str,
    relation: str,
    to_id: str,
    properties: Optional[dict] = None,
) -> dict:
    """Create a typed directed relationship between two entities/docs."""
    result = GRAPH.add(
        from_id=from_id, relation=relation, to_id=to_id, properties=properties
    )
    ENTITIES.log_change(
        "create", "relationship", result["rel_id"],
        {"from_id": from_id, "relation": relation, "to_id": to_id},
        _author(),
    )
    return result


@mcp.tool()
def ec_rel_query(
    from_id: Optional[str] = None,
    to_id: Optional[str] = None,
    relation: Optional[str] = None,
    depth: int = 1,
) -> dict:
    """Find relationships. Supports multi-hop traversal via `depth`."""
    edges = GRAPH.query(
        from_id=from_id, to_id=to_id, relation=relation, depth=depth
    )
    return {"relationships": edges}


@mcp.tool()
def ec_rel_delete(rel_id: str) -> dict:
    """Remove a relationship."""
    if not GRAPH.delete(rel_id):
        raise ValueError(f"Relationship not found: {rel_id!r}")
    ENTITIES.log_change("delete", "relationship", rel_id, None, _author())
    return {"status": "deleted", "rel_id": rel_id}


# ---- Utilities -----------------------------------------------------------

@mcp.tool()
def ec_stats() -> dict:
    """Overview of the vault — entity counts, doc counts, relationship counts."""
    types = ENTITIES.list_types()
    return {
        "entities": {t["name"]: t["entity_count"] for t in types},
        "entity_types": [t["name"] for t in types],
        "documents": DOCS.count(),
        "relationships": GRAPH.count(),
    }


@mcp.tool()
def ec_search(query: str, limit: int = 10) -> dict:
    """Universal search — merges semantic doc hits with structured entity hits.

    Used when the agent doesn't know which store to hit. Docs are scored
    by vector similarity; entities are scored by simple substring match
    on their JSON-serialized data (not as good as a real ranker, but
    enough for the unsure-which-store path).
    """
    results: list[dict] = []

    # Semantic hits from docs.
    for doc in DOCS.search(query=query, limit=limit):
        title = doc.get("title") or (doc.get("content") or "")[:80]
        results.append(
            {
                "type": "doc",
                "id": doc["doc_id"],
                "summary": title,
                "score": doc.get("similarity") or 0.0,
            }
        )

    # Naive entity match across every type. Fine for small vaults; if
    # this grows we can swap for FTS5 over a synthesized search column.
    needle = query.lower()
    for type_def in ENTITIES.list_types():
        out = ENTITIES.query_entities(type_name=type_def["name"], limit=200)
        for ent in out["entities"]:
            blob = json.dumps(ent["data"]).lower()
            if needle in blob:
                name = ent["data"].get("name") or ent["data"].get("title")
                summary = f"{type_def['name']}: {name}" if name else type_def["name"]
                results.append(
                    {
                        "type": "entity",
                        "id": ent["entity_id"],
                        "summary": summary,
                        "score": 0.5,  # rough — exact-match entities aren't ranked
                    }
                )

    results.sort(key=lambda r: r["score"], reverse=True)
    return {"results": results[:limit]}


@mcp.tool()
def ec_export() -> dict:
    """Export all data as JSON. For backup or migration."""
    types = ENTITIES.list_types()
    entities: list[dict] = []
    for type_def in types:
        out = ENTITIES.query_entities(type_name=type_def["name"], limit=10**9)
        entities.extend(
            {
                "entity_id": e["entity_id"],
                "type": e["type"],
                "data": e["data"],
                "created_at": e.get("created_at"),
                "updated_at": e.get("updated_at"),
            }
            for e in out["entities"]
        )
    return {
        "version": 1,
        "entity_types": [
            {
                "name": t["name"],
                "description": t["description"],
                "fields": t["fields"],
            }
            for t in types
        ],
        "entities": entities,
        "docs": DOCS.all_docs(),
        "relationships": GRAPH.all_edges(),
    }


@mcp.tool()
def ec_import(data: dict) -> dict:
    """Import data from a previous `ec_export`. Merges with existing data."""
    if not isinstance(data, dict):
        raise ValueError("`data` must be the exported JSON object")
    counts = {"entity_types": 0, "entities": 0, "docs": 0, "relationships": 0}

    for tdef in data.get("entity_types", []) or []:
        ENTITIES.define_type(
            name=tdef["name"],
            fields=tdef["fields"],
            description=tdef.get("description"),
        )
        counts["entity_types"] += 1

    for ent in data.get("entities", []) or []:
        # Re-create with a fresh validation pass; we accept that imported
        # IDs are reissued so we don't fight FK semantics on relationships
        # — those are imported by their (from_id, to_id) which are typed
        # IDs that callers control.
        new = ENTITIES.create_entity(
            type_name=ent["type"],
            data=ent["data"],
            created_by=_author(),
        )
        ent["_new_id"] = new["entity_id"]
        ent["_old_id"] = ent.get("entity_id")
        counts["entities"] += 1

    id_map: dict[str, str] = {
        ent["_old_id"]: ent["_new_id"]
        for ent in (data.get("entities") or [])
        if ent.get("_old_id") and ent.get("_new_id")
    }

    for doc in data.get("docs", []) or []:
        DOCS.import_doc(
            doc_id=doc["doc_id"],
            content=doc["content"],
            title=doc.get("title"),
            tags=doc.get("tags") or [],
            source=doc.get("source"),
        )
        counts["docs"] += 1

    for rel in data.get("relationships", []) or []:
        GRAPH.import_edge(
            rel_id=rel["rel_id"],
            from_id=id_map.get(rel["from_id"], rel["from_id"]),
            relation=rel["relation"],
            to_id=id_map.get(rel["to_id"], rel["to_id"]),
            properties=rel.get("properties"),
        )
        counts["relationships"] += 1

    return {"imported": counts}


# ---------------------------------------------------------------------------
# Auth middleware (ASGI)
# ---------------------------------------------------------------------------


class APIKeyMiddleware:
    """Validate X-API-Key on /mcp paths and bind name to a contextvar."""

    PROTECTED_PREFIXES = ("/mcp",)

    def __init__(self, app: ASGIApp, auth: APIKeyAuth) -> None:
        self.app = app
        self.auth = auth

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if not any(path.startswith(p) for p in self.PROTECTED_PREFIXES):
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        provided = headers.get("x-api-key") or _bearer_token(headers.get("authorization"))
        name = self.auth.validate(provided or "")
        if not name:
            response = JSONResponse(
                {"error": "unauthorized", "detail": "Valid X-API-Key header required"},
                status_code=401,
            )
            await response(scope, receive, send)
            return

        token = current_api_key_name.set(name)
        try:
            await self.app(scope, receive, send)
        finally:
            current_api_key_name.reset(token)


def _bearer_token(value: Optional[str]) -> Optional[str]:
    """Accept `Authorization: Bearer <key>` as a fallback to `X-API-Key`."""
    if not value:
        return None
    parts = value.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return None


# ---------------------------------------------------------------------------
# ASGI app composition
# ---------------------------------------------------------------------------


async def health(_request) -> Response:
    return JSONResponse({"status": "ok", "service": "encyclist"})


def build_app() -> ASGIApp:
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app):
        # Forward the inner Starlette app's lifespan so MCP's session
        # manager starts/stops with the outer app.
        async with mcp_app.router.lifespan_context(app):
            yield

    outer = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Mount("/", app=mcp_app),
        ],
        lifespan=lifespan,
    )
    return APIKeyMiddleware(outer, AUTH)


app = build_app()


# ---------------------------------------------------------------------------
# CLI entry point: `python -m src.server` for local dev
# ---------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "src.server:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )

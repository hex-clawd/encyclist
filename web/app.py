"""FastAPI app for the Encyclist web UI.

Server-side renders Jinja2 templates and proxies all data through the
remote Encyclist MCP server (`web.mcp_client`). No local DB.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markdown import markdown as render_markdown
from markupsafe import Markup

# Load .env before importing the MCP client (which reads env on call).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from web.mcp_client import MCPConfigError, MCPToolError, call_tool, safe_call  # noqa: E402

# ---------------------------------------------------------------------------
# App + templates
# ---------------------------------------------------------------------------

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"

app = FastAPI(title="Encyclist Web UI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _markdown_filter(value: Optional[str]) -> Markup:
    if not value:
        return Markup("")
    html = render_markdown(value, extensions=["fenced_code", "tables", "nl2br"])
    return Markup(html)


def _id_kind(any_id: Optional[str]) -> Optional[str]:
    """Classify an Encyclist ID by its prefix."""
    if not any_id:
        return None
    if any_id.startswith("ent_"):
        return "entity"
    if any_id.startswith("doc_"):
        return "doc"
    if any_id.startswith("rel_"):
        return "relationship"
    return "unknown"


def _id_url(any_id: Optional[str]) -> Optional[str]:
    kind = _id_kind(any_id)
    if kind == "entity":
        return f"/entity/{any_id}"
    if kind == "doc":
        return f"/doc/{any_id}"
    return None


templates.env.filters["markdown"] = _markdown_filter
templates.env.filters["id_kind"] = _id_kind
templates.env.filters["id_url"] = _id_url
templates.env.globals["site_name"] = "Encyclist"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _entity_display_name(entity: dict) -> str:
    data = entity.get("data") or {}
    return (
        data.get("name")
        or data.get("title")
        or data.get("label")
        or entity.get("entity_id", "")
    )


async def _fetch_label(any_id: str) -> str:
    """Best-effort human label for a relationship endpoint."""
    kind = _id_kind(any_id)
    try:
        if kind == "entity":
            ent = await call_tool("ec_entity_get", {"entity_id": any_id})
            if isinstance(ent, dict):
                return _entity_display_name(ent)
        elif kind == "doc":
            doc = await call_tool("ec_doc_get", {"doc_id": any_id})
            if isinstance(doc, dict):
                return doc.get("title") or any_id
    except Exception:
        pass
    return any_id


def _coerce_form_value(field_type: str, raw: str) -> Any:
    """Convert a form-submitted string into the right Python type."""
    if raw is None or raw == "":
        return None
    if field_type in ("string", "text"):
        return raw
    if field_type == "int":
        return int(raw)
    if field_type == "float":
        return float(raw)
    if field_type == "bool":
        return raw.lower() in ("true", "1", "yes", "on")
    if field_type == "json":
        return json.loads(raw)
    return raw


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


@app.exception_handler(MCPConfigError)
async def _config_handler(request: Request, exc: MCPConfigError):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "title": "Configuration error",
            "message": str(exc),
            "hint": "Copy `.env.example` to `.env` and fill in `ENCYCLIST_URL` and `ENCYCLIST_API_KEY`.",
        },
        status_code=500,
    )


@app.exception_handler(MCPToolError)
async def _tool_handler(request: Request, exc: MCPToolError):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "request": request,
            "title": "MCP server error",
            "message": str(exc),
            "hint": "The remote Encyclist server returned an error. Check the URL, API key, and that the server is running.",
        },
        status_code=502,
    )


# ---------------------------------------------------------------------------
# Routes — Home
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    stats = await safe_call("ec_stats", {}, default={"entities": {}, "documents": 0, "relationships": 0, "entity_types": []})
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []

    # Recent activity: pull a handful of entities (per type) and docs, then
    # sort by created_at and slice to 10. Vault is small; fine for v1.
    recent: list[dict] = []
    for t in types:
        out = await safe_call(
            "ec_entity_query",
            {"type": t["name"], "limit": 20},
            default={"entities": []},
        ) or {}
        for ent in out.get("entities", []):
            recent.append(
                {
                    "kind": "entity",
                    "id": ent["entity_id"],
                    "title": _entity_display_name(ent),
                    "subtitle": t["name"],
                    "created_at": ent.get("created_at"),
                    "updated_at": ent.get("updated_at"),
                }
            )

    docs = await safe_call("ec_doc_list", {"limit": 20}, default={"docs": []}) or {}
    for doc in docs.get("docs", []):
        recent.append(
            {
                "kind": "doc",
                "id": doc["doc_id"],
                "title": doc.get("title") or doc["doc_id"],
                "subtitle": ", ".join(doc.get("tags") or []) or "document",
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("created_at"),
            }
        )

    recent.sort(key=lambda x: x.get("updated_at") or x.get("created_at") or "", reverse=True)

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "request": request,
            "stats": stats,
            "types": types,
            "recent": recent[:10],
        },
    )


# ---------------------------------------------------------------------------
# Routes — Entity
# ---------------------------------------------------------------------------


@app.get("/entity/{entity_id}", response_class=HTMLResponse)
async def entity_page(request: Request, entity_id: str):
    entity = await call_tool("ec_entity_get", {"entity_id": entity_id})
    if not isinstance(entity, dict):
        raise HTTPException(404, "Entity not found")

    type_def = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in type_def if t["name"] == entity.get("type")), None)

    rels = await safe_call(
        "ec_rel_query", {"from_id": entity_id, "depth": 1}, default={"relationships": []}
    ) or {"relationships": []}
    inbound = await safe_call(
        "ec_rel_query", {"to_id": entity_id, "depth": 1}, default={"relationships": []}
    ) or {"relationships": []}

    # Resolve labels for each endpoint we'll display.
    label_cache: dict[str, str] = {}
    for edge in rels["relationships"] + inbound["relationships"]:
        for nid in (edge["from_id"], edge["to_id"]):
            if nid not in label_cache and nid != entity_id:
                label_cache[nid] = await _fetch_label(nid)
    label_cache[entity_id] = _entity_display_name(entity)

    name = _entity_display_name(entity)
    related_docs = await safe_call(
        "ec_doc_search", {"query": name, "limit": 5}, default=[]
    ) or []

    return templates.TemplateResponse(
        request,
        "entity.html",
        {
            "request": request,
            "entity": entity,
            "name": name,
            "type_meta": type_meta,
            "outgoing": rels["relationships"],
            "incoming": inbound["relationships"],
            "labels": label_cache,
            "related_docs": related_docs,
        },
    )


@app.get("/entity/{entity_id}/edit", response_class=HTMLResponse)
async def entity_edit_form(request: Request, entity_id: str):
    entity = await call_tool("ec_entity_get", {"entity_id": entity_id})
    if not isinstance(entity, dict):
        raise HTTPException(404, "Entity not found")
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in types if t["name"] == entity["type"]), None)
    if type_meta is None:
        raise HTTPException(500, "Entity type definition not found")
    return templates.TemplateResponse(
        request,
        "entity_edit.html",
        {
            "request": request,
            "entity": entity,
            "type_meta": type_meta,
        },
    )


@app.post("/entity/{entity_id}/update")
async def entity_update(request: Request, entity_id: str):
    form = await request.form()
    existing = await call_tool("ec_entity_get", {"entity_id": entity_id})
    if not isinstance(existing, dict):
        raise HTTPException(404, "Entity not found")
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in types if t["name"] == existing["type"]), None)
    if type_meta is None:
        raise HTTPException(500, "Entity type definition not found")

    patch: dict[str, Any] = {}
    for fname, spec in type_meta["fields"].items():
        if fname not in form:
            continue
        raw = form.get(fname)
        if spec["type"] == "bool":
            patch[fname] = raw is not None and str(raw).lower() in ("true", "1", "on", "yes")
            continue
        if raw is None or raw == "":
            continue
        try:
            patch[fname] = _coerce_form_value(spec["type"], str(raw))
        except (ValueError, json.JSONDecodeError) as e:
            raise HTTPException(400, f"Invalid value for {fname}: {e}")
    # Bool fields not in form (unchecked) → set to False so they actually save.
    for fname, spec in type_meta["fields"].items():
        if spec["type"] == "bool" and fname not in patch:
            patch[fname] = False

    await call_tool("ec_entity_update", {"entity_id": entity_id, "data": patch})
    return RedirectResponse(f"/entity/{entity_id}", status_code=303)


@app.post("/entity/{entity_id}/delete")
async def entity_delete(entity_id: str):
    await call_tool("ec_entity_delete", {"entity_id": entity_id})
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Type index
# ---------------------------------------------------------------------------


@app.get("/type/{type_name}", response_class=HTMLResponse)
async def type_index(request: Request, type_name: str):
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in types if t["name"] == type_name), None)
    if type_meta is None:
        raise HTTPException(404, f"Entity type {type_name!r} not found")

    out = await call_tool("ec_entity_query", {"type": type_name, "limit": 200})
    entities = out.get("entities", []) if isinstance(out, dict) else []

    # Pick a few "key fields" to show in the table — name/title first,
    # then up to 3 of the type's fields.
    key_fields: list[str] = []
    for preferred in ("name", "title", "label"):
        if preferred in type_meta["fields"] and preferred not in key_fields:
            key_fields.append(preferred)
    for fname in type_meta["fields"]:
        if fname not in key_fields:
            key_fields.append(fname)
        if len(key_fields) >= 5:
            break

    return templates.TemplateResponse(
        request,
        "type_index.html",
        {
            "request": request,
            "type_meta": type_meta,
            "entities": entities,
            "key_fields": key_fields,
            "total": out.get("total", len(entities)) if isinstance(out, dict) else len(entities),
        },
    )


# ---------------------------------------------------------------------------
# Routes — Document
# ---------------------------------------------------------------------------


@app.get("/doc/new", response_class=HTMLResponse)
async def doc_new_form(request: Request):
    return templates.TemplateResponse(request, "doc_new.html", {"request": request})


@app.post("/doc/new")
async def doc_new_submit(
    title: str = Form(""),
    tags: str = Form(""),
    source: str = Form(""),
    content: str = Form(...),
):
    args: dict[str, Any] = {"content": content}
    if title.strip():
        args["title"] = title.strip()
    if tags.strip():
        args["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if source.strip():
        args["source"] = source.strip()
    result = await call_tool("ec_doc_add", args)
    doc_id = result.get("doc_id") if isinstance(result, dict) else None
    return RedirectResponse(f"/doc/{doc_id}" if doc_id else "/", status_code=303)


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
async def doc_page(request: Request, doc_id: str):
    doc = await call_tool("ec_doc_get", {"doc_id": doc_id})
    if not isinstance(doc, dict):
        raise HTTPException(404, "Document not found")
    related = await safe_call(
        "ec_doc_search",
        {"query": (doc.get("title") or doc.get("content") or "")[:200], "limit": 5},
        default=[],
    ) or []
    related = [d for d in related if d.get("doc_id") != doc_id][:4]
    return templates.TemplateResponse(
        "doc.html",
        {"request": request, "doc": doc, "related": related},
    )


@app.get("/doc/{doc_id}/edit", response_class=HTMLResponse)
async def doc_edit_form(request: Request, doc_id: str):
    doc = await call_tool("ec_doc_get", {"doc_id": doc_id})
    if not isinstance(doc, dict):
        raise HTTPException(404, "Document not found")
    return templates.TemplateResponse(
        "doc_edit.html", {"request": request, "doc": doc}
    )


@app.post("/doc/{doc_id}/update")
async def doc_update(
    doc_id: str,
    title: str = Form(""),
    tags: str = Form(""),
    content: str = Form(...),
):
    args: dict[str, Any] = {
        "doc_id": doc_id,
        "content": content,
        "title": title.strip() or None,
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    }
    await call_tool("ec_doc_update", args)
    return RedirectResponse(f"/doc/{doc_id}", status_code=303)


@app.post("/doc/{doc_id}/delete")
async def doc_delete(doc_id: str):
    await call_tool("ec_doc_delete", {"doc_id": doc_id})
    return RedirectResponse("/", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Search
# ---------------------------------------------------------------------------


@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = Query("", alias="q")):
    results: list[dict] = []
    if q.strip():
        out = await safe_call("ec_search", {"query": q, "limit": 25}, default={"results": []}) or {}
        results = out.get("results", [])
    entity_results = [r for r in results if r.get("type") == "entity"]
    doc_results = [r for r in results if r.get("type") == "doc"]
    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "request": request,
            "q": q,
            "entity_results": entity_results,
            "doc_results": doc_results,
            "total": len(results),
        },
    )


@app.get("/search/suggest", response_class=HTMLResponse)
async def search_suggest(request: Request, q: str = Query("", alias="q")):
    if not q.strip() or len(q.strip()) < 2:
        return HTMLResponse("")
    out = await safe_call("ec_search", {"query": q, "limit": 8}, default={"results": []}) or {}
    return templates.TemplateResponse(
        "partials/search_suggest.html",
        {"request": request, "q": q, "results": out.get("results", [])},
    )


# ---------------------------------------------------------------------------
# Routes — Create entity
# ---------------------------------------------------------------------------


@app.get("/create", response_class=HTMLResponse)
async def create_entity_form(request: Request, type: Optional[str] = None):  # noqa: A002
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in types if t["name"] == type), None) if type else None
    return templates.TemplateResponse(
        request,
        "create.html",
        {
            "request": request,
            "types": types,
            "selected": type,
            "type_meta": type_meta,
        },
    )


@app.post("/create")
async def create_entity_submit(request: Request):
    form = await request.form()
    type_name = form.get("__type")
    if not type_name:
        raise HTTPException(400, "Missing entity type")
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    type_meta = next((t for t in types if t["name"] == type_name), None)
    if type_meta is None:
        raise HTTPException(400, f"Unknown entity type: {type_name!r}")

    data: dict[str, Any] = {}
    for fname, spec in type_meta["fields"].items():
        if spec["type"] == "bool":
            data[fname] = form.get(fname) is not None and str(form.get(fname)).lower() in ("true", "1", "on", "yes")
            continue
        raw = form.get(fname)
        if raw is None or raw == "":
            continue
        try:
            data[fname] = _coerce_form_value(spec["type"], str(raw))
        except (ValueError, json.JSONDecodeError) as e:
            raise HTTPException(400, f"Invalid value for {fname}: {e}")

    result = await call_tool("ec_entity_create", {"type": type_name, "data": data})
    entity_id = result.get("entity_id") if isinstance(result, dict) else None
    return RedirectResponse(f"/entity/{entity_id}" if entity_id else "/", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Relationships
# ---------------------------------------------------------------------------


@app.get("/relations", response_class=HTMLResponse)
async def relations_page(request: Request):
    out = await safe_call("ec_rel_query", {"depth": 1}, default={"relationships": []}) or {"relationships": []}
    edges = out["relationships"][:50]
    label_cache: dict[str, str] = {}
    for edge in edges:
        for nid in (edge["from_id"], edge["to_id"]):
            if nid not in label_cache:
                label_cache[nid] = await _fetch_label(nid)
    return templates.TemplateResponse(
        "relations.html",
        {"request": request, "edges": edges, "labels": label_cache},
    )


@app.post("/relations")
async def relations_add(
    from_id: str = Form(...),
    relation: str = Form(...),
    to_id: str = Form(...),
    properties: str = Form(""),
):
    args: dict[str, Any] = {
        "from_id": from_id.strip(),
        "relation": relation.strip(),
        "to_id": to_id.strip(),
    }
    if properties.strip():
        try:
            args["properties"] = json.loads(properties)
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"Invalid properties JSON: {e}")
    await call_tool("ec_rel_add", args)
    return RedirectResponse("/relations", status_code=303)


@app.post("/relations/{rel_id}/delete")
async def relations_delete(rel_id: str):
    await call_tool("ec_rel_delete", {"rel_id": rel_id})
    return RedirectResponse("/relations", status_code=303)


# ---------------------------------------------------------------------------
# Routes — Graph explorer
# ---------------------------------------------------------------------------


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request, entity_id: Optional[str] = None, type: Optional[str] = None):  # noqa: A002
    types = await safe_call("ec_entity_type_list", {}, default=[]) or []
    return templates.TemplateResponse(
        request,
        "graph.html",
        {
            "request": request,
            "types": types,
            "seed_entity_id": entity_id,
            "seed_type": type,
        },
    )


@app.get("/graph/data")
async def graph_data(entity_id: Optional[str] = None, type: Optional[str] = None):  # noqa: A002
    """Return a small node/edge subgraph as JSON.

    - With `entity_id`: the 1-hop neighborhood of that entity.
    - With `type`: every entity of that type, plus relationships among them.
    - Otherwise: a sample of recent relationships (capped) and their endpoints.
    """
    edges_raw: list[dict] = []
    seed_ids: set[str] = set()

    if entity_id:
        seed_ids.add(entity_id)
        out_a = await safe_call("ec_rel_query", {"from_id": entity_id}, default={"relationships": []}) or {}
        out_b = await safe_call("ec_rel_query", {"to_id": entity_id}, default={"relationships": []}) or {}
        edges_raw = out_a.get("relationships", []) + out_b.get("relationships", [])
    elif type:
        out = await safe_call("ec_entity_query", {"type": type, "limit": 200}, default={"entities": []}) or {}
        for e in out.get("entities", []):
            seed_ids.add(e["entity_id"])
        # Pull all edges, filter to those touching this type.
        all_edges = await safe_call("ec_rel_query", {}, default={"relationships": []}) or {}
        for edge in all_edges.get("relationships", []):
            if edge["from_id"] in seed_ids or edge["to_id"] in seed_ids:
                edges_raw.append(edge)
    else:
        all_edges = await safe_call("ec_rel_query", {}, default={"relationships": []}) or {}
        edges_raw = all_edges.get("relationships", [])[:50]

    # Dedupe edges by rel_id and collect node IDs.
    seen: set[str] = set()
    edges: list[dict] = []
    node_ids: set[str] = set(seed_ids)
    for e in edges_raw:
        if e["rel_id"] in seen:
            continue
        seen.add(e["rel_id"])
        edges.append(
            {
                "id": e["rel_id"],
                "source": e["from_id"],
                "target": e["to_id"],
                "label": e["relation"],
            }
        )
        node_ids.add(e["from_id"])
        node_ids.add(e["to_id"])

    nodes: list[dict] = []
    for nid in node_ids:
        kind = _id_kind(nid)
        label = await _fetch_label(nid)
        nodes.append({"id": nid, "label": label, "kind": kind or "unknown"})

    return JSONResponse({"nodes": nodes, "edges": edges})


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    import uvicorn

    uvicorn.run(
        "web.app:app",
        host=os.environ.get("WEB_HOST", "127.0.0.1"),
        port=int(os.environ.get("WEB_PORT", "8080")),
        reload=False,
    )


if __name__ == "__main__":
    main()

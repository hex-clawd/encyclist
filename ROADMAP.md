# Encyclist — Development Roadmap & Progress

> **This file is the single source of truth for project progress.** Update after every work session.
> Last updated: 2026-04-25

## Status: 🔵 SPECS COMPLETE — Ready for Phase 1 development

---

## Phase 1 — Core MCP Server (MVP)

### Step 1: Project Setup
- [ ] Create `pyproject.toml` with dependencies (mcp, chromadb, uvicorn)
- [ ] Create `Dockerfile`
- [ ] Create `fly.toml`
- [ ] Create `.claude/CLAUDE.md` project context file for CC
- [ ] Verify: `pip install -e .` works, imports resolve

### Step 2: Entity Store (SQLite)
- [ ] `src/config.py` — data directory, DB path, config loading
- [ ] `src/entity_store.py` — schema init, entity type CRUD, entity CRUD, query with filters
- [ ] `tests/test_entity_store.py` — TDD: define type, create entity, query, update, delete
- [ ] Verify: all entity store tests pass

### Step 3: Doc Store (ChromaDB)
- [ ] `src/doc_store.py` — add, search, get, update, list, delete documents
- [ ] `tests/test_doc_store.py` — TDD: add doc, semantic search finds it, update, delete
- [ ] Verify: all doc store tests pass

### Step 4: Relationship Graph
- [ ] `src/graph.py` — add, query (with depth), delete relationships
- [ ] `tests/test_graph.py` — TDD: link entity→entity, entity→doc, multi-hop traversal
- [ ] Verify: all graph tests pass

### Step 5: Auth & API Keys
- [ ] `src/auth.py` — API key hash storage, validation, key management tools
- [ ] `tests/test_auth.py` — TDD: create key, validate, revoke
- [ ] Verify: auth tests pass

### Step 6: MCP Server Wiring
- [ ] `src/server.py` — StreamableHTTP server, wire all tools, auth middleware
- [ ] Wire entity store tools (ec_entity_type_define, ec_entity_create, ec_entity_query, etc.)
- [ ] Wire doc store tools (ec_doc_add, ec_doc_search, etc.)
- [ ] Wire relationship tools (ec_rel_add, ec_rel_query, ec_rel_delete)
- [ ] Wire utility tools (ec_stats, ec_search, ec_export, ec_import)
- [ ] Wire auth tools (ec_key_create, ec_key_list, ec_key_revoke)
- [ ] `/health` endpoint
- [ ] Verify: server starts, tools respond over HTTP

### Step 7: Integration Test
- [ ] End-to-end test: define type → create entities → link → search → query → export
- [ ] Verify: full workflow works via HTTP

### Step 8: Fly.io Deployment
- [ ] Build and test Docker image locally
- [ ] `fly apps create encyclist`
- [ ] `fly volumes create encyclist_data --size 1 --region ams`
- [ ] Set secrets (API keys)
- [ ] `fly deploy`
- [ ] Verify: `curl https://encyclist.fly.dev/health` returns ok
- [ ] Connect Hermes MCP client to it

---

## Phase 2 — Multi-agent & Polish (NOT STARTED)
- [ ] Agent identity tracking (who wrote what)
- [ ] Change history / audit log display
- [ ] Conflict resolution for concurrent writes
- [ ] Export/import JSON backup
- [ ] Optional web UI (if designer wants it)

---

## Phase 3 — Web UI (NOT STARTED)
- [ ] FastAPI + HTMX/Jinja2 browse interface
- [ ] Entity table view
- [ ] Doc reader (rendered markdown)
- [ ] Inline editing

---

## Specs (ALL COMPLETE ✅)
- [x] `specs/00-overview.md` — architecture, tech stack, Fly.io deployment
- [x] `specs/01-mcp-tools.md` — 17 MCP tools, full API spec
- [x] `specs/02-data-model.md` — SQLite schema, ChromaDB, auth, ID scheme
- [x] `specs/03-deployment.md` — Dockerfile, fly.toml, volume, auto-wake

---

## Session Log

| Date | What happened |
|------|---------------|
| 2026-04-25 | Project created as "GameVault", renamed to Encyclist. Specs written. Fly.io chosen for hosting. Claude Code confirmed working. Boris Cherny AGENTS.md reviewed. |

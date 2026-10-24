# Encyclist — Development Roadmap & Progress

> **This file is the single source of truth for project progress.** Update after every work session.
> Last updated: 2026-04-25

## Status: 🟢 PHASE 1 STEPS 1–7 COMPLETE — 26/26 tests passing, all 23 MCP tools wired

---

## Phase 1 — Core MCP Server (MVP)

### Step 1: Project Setup
- [x] Create `pyproject.toml` with dependencies (mcp, chromadb, uvicorn)
- [x] Create `Dockerfile`
- [x] Create `fly.toml`
- [ ] Create `.claude/CLAUDE.md` project context file for CC
- [x] Verify: `pip install -e .` works, imports resolve

### Step 2: Entity Store (SQLite)
- [x] `src/config.py` — data directory, DB path, config loading
- [x] `src/entity_store.py` — schema init, entity type CRUD, entity CRUD, query with filters
- [x] `tests/test_entity_store.py` — TDD: define type, create entity, query, update, delete
- [x] Verify: all entity store tests pass (9/9)

### Step 3: Doc Store (ChromaDB)
- [x] `src/doc_store.py` — add, search, get, update, list, delete documents
- [x] `tests/test_doc_store.py` — TDD: add doc, semantic search finds it, update, delete
- [x] Verify: all doc store tests pass (4/4)

### Step 4: Relationship Graph
- [x] `src/graph.py` — add, query (with depth), delete relationships
- [x] `tests/test_graph.py` — TDD: link entity→entity, entity→doc, multi-hop traversal
- [x] Verify: all graph tests pass (4/4)

### Step 5: Auth & API Keys
- [x] `src/auth.py` — API key hash storage, validation, key management tools
- [x] `tests/test_auth.py` — TDD: create key, validate, revoke
- [x] Verify: auth tests pass (4/4)

### Step 6: MCP Server Wiring
- [x] `src/server.py` — StreamableHTTP server, wire all tools, auth middleware
- [x] Wire entity store tools (ec_entity_type_define, ec_entity_create, ec_entity_query, etc.)
- [x] Wire doc store tools (ec_doc_add, ec_doc_search, etc.)
- [x] Wire relationship tools (ec_rel_add, ec_rel_query, ec_rel_delete)
- [x] Wire utility tools (ec_stats, ec_search, ec_export, ec_import)
- [x] Wire auth tools (ec_key_create, ec_key_list, ec_key_revoke)
- [x] `/health` endpoint
- [x] Verify: server starts, tools respond over HTTP (23 tools listed via `tools/list`)

### Step 7: Integration Test
- [x] End-to-end test: define type → create entities → link → search → query → export → import → stats
- [x] Verify: full workflow works against real SQLite + ChromaDB stores

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
| 2026-04-25 | Phase 1 Steps 1–6 implementation verified. All 25 unit tests pass (auth 4, doc_store 4, entity_store 9, graph 4, server 4). `from src.server import app` succeeds. 20 MCP tools wired (6 doc, 7 entity, 3 rel, 4 utility). Outstanding: `.claude/CLAUDE.md` not created; `ec_key_*` auth tools not wired; Step 7 e2e HTTP roundtrip and Step 8 Fly.io deployment still TODO. |
| 2026-04-25 | Phase 1 Step 6 finished: wired `ec_key_create` / `ec_key_list` / `ec_key_revoke` (23 MCP tools total). Phase 1 Step 7 done: `tests/test_integration.py` exercises define-type → create entities → semantic search → structured query → entity↔entity + entity↔doc links → multi-hop traversal → JSON export → import into a fresh vault → stats verification. Test suite: 26/26 passing (auth 4, doc_store 4, entity_store 9, graph 4, integration 1, server 4). Remaining: `.claude/CLAUDE.md` and Step 8 Fly.io deployment. |

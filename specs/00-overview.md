# Encyclist — Project Overview

## What

Self-hosted, MCP-native shared knowledge base for collaborative projects. One endpoint, two storage engines — semantic (ChromaDB) for unstructured docs and exact (SQLite) for structured tabular data. AI agents are the primary interface. Humans interact through their agents or an optional lightweight web UI.

Named after encyclopedia + "-ist" suffix (same pattern as Creaturist — the game project this was originally built for).

## Who

- **Matej** — developer, drives AI-assisted code generation from project data via Hermes
- **Friend** — game/product designer, lives in Perplexity chats and scattered .md files, dumps ideas and data through their agent

## Why

Current state: designer's work lives in chat history and loose files. Not shareable, not queryable by agents, not structured enough for code generation. Need a single system that:

1. Accepts both prose/design docs AND structured entity data
2. Both agents can read/write via MCP
3. Semantic search for "find that idea about the volcano boss" — zero organization required
4. Exact queries for "all creatures with HP > 100 AND element = fire" — precision when needed
5. Self-hosted, no third-party dependencies

## Architecture

```
┌──────────────────────────────────────┐
│        Encyclist MCP Server          │
│      (Fly.io, StreamableHTTP)        │
│                                      │
│  ┌────────────┐  ┌────────────────┐  │
│  │ Doc Store  │  │ Entity Store   │  │
│  │ (ChromaDB) │  │ (SQLite)       │  │
│  │            │  │                │  │
│  │ Design docs│  │ Any structured │  │
│  │ PRDs       │  │ data: creatures│  │
│  │ Lore       │  │ items, quests, │  │
│  │ Meeting    │  │ locations,     │  │
│  │ notes      │  │ abilities...   │  │
│  │ Random     │  │ (extensible)   │  │
│  │ ideas      │  │                │  │
│  └────────────┘  └────────────────┘  │
│         ↕             ↕              │
│  ┌─────────────────────────────────┐ │
│  │     Relationship Graph          │ │
│  │  quest → requires → item        │ │
│  │  creature → drops → item        │ │
│  │  quest → happens_in → location  │ │
│  └─────────────────────────────────┘ │
│                                      │
│  Persistent Volume: /data            │
│  Auth: API key per agent             │
└──────────────────────────────────────┘
         ↕ MCP over HTTPS
    ┌─────────┐  ┌─────────┐
    │ Hermes  │  │ Friend's│
    │ (Matej) │  │  Agent  │
    └─────────┘  └─────────┘
```

## Tech Stack

- **Python 3.11+** — MCP server implementation
- **SQLite** — structured entity storage, on Fly persistent volume
- **ChromaDB** — semantic vector storage for docs (proven engine, same as MemPalace)
- **MCP SDK** (`mcp` package) — StreamableHTTP transport
- **Fly.io** — hosting, persistent volume, auto-wake on traffic
- **FastAPI + Jinja2** (optional, phase 2) — lightweight web UI

## Deployment: Fly.io

Encyclist runs as a single Fly.io app with:

- **MCP over StreamableHTTP** — agents POST to `https://encyclist.fly.dev/mcp`
- **API key auth** — each agent gets a key, passed in header `X-API-Key`
- **Persistent volume** (1GB) mounted at `/data` — holds SQLite DB + ChromaDB directory
- **Auto-stop/start** — `auto_stop_machines = true`, `min_machines_running = 0`. Sleeps when idle, wakes on incoming request. Zero cost when not in use.
- **Backup** — `ec_export` dumps everything to JSON. Can be scripted as a cron.

### fly.toml (key settings)
```toml
app = "encyclist"
primary_region = "ams"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[mounts]
  source = "encyclist_data"
  destination = "/data"
```

## Key Design Decisions

### Agents first, humans second
The MCP interface IS the primary interface. Every operation goes through MCP tools. A web UI, if built, calls the same backend.

### Unstructured and structured live together
Design docs, random brainstorms, PRDs → ChromaDB. Structured data with properties → SQLite. The MCP router knows which store to hit based on the tool called. Cross-references via the relationship graph.

### Extensible entity types
Don't hardcode entity types. They are defined by the users and created on the fly. "Add a new entity type called 'dungeons' with fields: name, difficulty, boss, loot_table" → done.

### Semantic search as default
For human-style queries ("what was that idea about..."), semantic search is the default. For code generation and exact filters, SQL queries. The agent decides which to use based on context.

### Self-contained
Single Fly.io app. SQLite file + ChromaDB directory on a persistent volume. Back up by exporting to JSON. Restore by importing.

### Universal, not game-specific
Built for the Creaturist game project first, but the tool itself is generic. Any project with unstructured docs + structured data + multi-agent access can use it.

## File Structure

```
~/Projects/encyclist/
├── specs/               # Design specs
│   ├── 00-overview.md
│   ├── 01-mcp-tools.md
│   ├── 02-data-model.md
│   └── 03-deployment.md
├── docs/
│   └── plans/           # Implementation plans
├── src/
│   ├── server.py        # MCP server entry point (StreamableHTTP)
│   ├── doc_store.py     # ChromaDB semantic store
│   ├── entity_store.py  # SQLite structured store
│   ├── graph.py         # Relationship graph
│   ├── auth.py          # API key authentication
│   └── config.py        # Configuration
├── tests/
├── data/                # Runtime data (gitignored)
│   ├── encyclist.db     # SQLite
│   └── chroma/          # ChromaDB
├── Dockerfile
├── fly.toml
├── pyproject.toml
└── README.md
```

## Phases

### Phase 1 — Core MCP Server (MVP)
- Doc store: add, search, list, delete documents
- Entity store: define types, CRUD entities, exact queries
- Relationship graph: link entities to each other and to docs
- API key auth
- Fly.io deployment with persistent volume
- ~300-400 lines, pure Python

### Phase 2 — Multi-agent & Polish
- Agent identity tracking (who wrote what)
- Change history / audit log
- Conflict resolution for concurrent writes
- Export/import (dump to JSON, restore)
- Web UI for browsing (if designer wants it)

### Phase 3 — Web UI (if needed)
- Lightweight FastAPI + HTMX/Jinja2
- Browse entities in table view
- Read docs in rendered markdown
- Edit entities inline
- Only if the designer actually wants it

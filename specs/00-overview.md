# GameVault — Project Overview

## What

Self-hosted, MCP-native knowledge base for game development. One endpoint, two storage engines — semantic (ChromaDB) for unstructured docs and exact (SQLite) for structured game entities. AI agents are the primary interface. Humans interact through their agents or an optional lightweight web UI.

## Who

- **Matej** — developer, drives AI-assisted code generation from game data
- **Friend** — game/product designer, lives in Perplexity chats and scattered .md files, needs to dump ideas and structured data through their agent

## Why

Current state: designer's work lives in chat history and loose files. Not shareable, not queryable by agents, not structured enough for code generation. Need a single system that:

1. Accepts both prose/design docs AND structured entity data
2. Both agents can read/write via MCP
3. Semantic search for "find that idea about the volcano boss" — zero organization required
4. Exact queries for "all creatures with HP > 100 AND element = fire" — game balance needs precision
5. Self-hosted, no third-party dependencies

## Architecture

```
┌──────────────────────────────────────┐
│          GameVault MCP Server        │
│         (stdio, one process)         │
│                                      │
│  ┌────────────┐  ┌────────────────┐  │
│  │ Doc Store  │  │ Entity Store   │  │
│  │ (ChromaDB) │  │ (SQLite)       │  │
│  │            │  │                │  │
│  │ Design docs│  │ Creatures      │  │
│  │ PRDs       │  │ Items          │  │
│  │ Lore       │  │ Locations      │  │
│  │ Meeting    │  │ Quests         │  │
│  │ notes      │  │ NPCs           │  │
│  │ Random     │  │ Abilities      │  │
│  │ ideas      │  │ (extensible)   │  │
│  └────────────┘  └────────────────┘  │
│         ↕             ↕              │
│  ┌─────────────────────────────────┐ │
│  │     Relationship Graph          │ │
│  │  quest → requires → item        │ │
│  │  creature → drops → item        │ │
│  │  quest → happens_in → location  │ │
│  └─────────────────────────────────┘ │
└──────────────────────────────────────┘
         ↕ MCP (stdio)
    ┌─────────┐  ┌─────────┐
    │ Hermes  │  │ Friend's│
    │ (Matej) │  │  Agent  │
    └─────────┘  └─────────┘
```

## Tech Stack

- **Python 3.11+** — MCP server implementation
- **SQLite** — structured entity storage, zero infra
- **ChromaDB** — semantic vector storage for docs (same engine as MemPalace, proven)
- **MCP SDK** (`mcp` package) — stdio transport, standard protocol
- **FastAPI + Jinja2** (optional, phase 2) — lightweight web UI for the designer

## Key Design Decisions

### Agents first, humans second
The MCP interface IS the primary interface. Every operation goes through MCP tools. A web UI, if built, calls the same backend.

### Unstructured and structured live together
Design docs, random brainstorms, PRDs → ChromaDB. Game entities with properties → SQLite. The MCP router knows which store to hit based on the tool called. Cross-references via the relationship graph.

### Extensible entity types
Don't hardcode "creatures, items, quests." Entity types are defined by the designers and created on the fly. "Add a new entity type called 'dungeons' with fields: name, difficulty, boss, loot_table" → done.

### Semantic search as default
For human-style queries ("what was that idea about..."), semantic search is the default. For code generation and game balance, exact SQL queries. The agent decides which to use based on context.

### Self-contained
Single process. No Docker, no cloud, no accounts. SQLite file + ChromaDB directory. Back up by copying the folder.

## File Structure

```
~/Projects/gamevault/
├── specs/               # Design specs (this folder)
│   ├── 00-overview.md
│   ├── 01-mcp-tools.md
│   ├── 02-data-model.md
│   └── 03-implementation-plan.md
├── docs/
│   └── plans/           # Implementation plans
├── src/
│   ├── server.py        # MCP server entry point
│   ├── doc_store.py     # ChromaDB semantic store
│   ├── entity_store.py  # SQLite structured store
│   ├── graph.py         # Relationship graph
│   ├── router.py        # Query routing logic
│   └── config.py        # Configuration
├── tests/
│   ├── test_doc_store.py
│   ├── test_entity_store.py
│   └── test_graph.py
├── data/                # Runtime data (gitignored)
│   ├── gamevault.db     # SQLite
│   └── chroma/          # ChromaDB
├── pyproject.toml
└── README.md
```

## Phases

### Phase 1 — Core MCP Server (MVP)
- Doc store: add, search, list, delete documents
- Entity store: define types, CRUD entities, exact queries
- Relationship graph: link entities to each other and to docs
- ~200-300 lines, pure Python, works immediately

### Phase 2 — Multi-agent & Polish
- Agent identity tracking (who wrote what)
- Change history / audit log
- Conflict resolution for concurrent writes
- Export/import (dump to JSON, restore)

### Phase 3 — Web UI (if needed)
- Lightweight FastAPI + HTMX/Jinja2
- Browse entities in table view
- Read docs in rendered markdown
- Edit entities inline
- Only if the designer actually wants it

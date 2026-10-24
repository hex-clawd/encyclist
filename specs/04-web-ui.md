# Encyclist Web UI — Local Wikipedia Browser

## Overview

A local web application that connects to an Encyclist MCP server (StreamableHTTP) and provides a Wikipedia-style browsing interface for the knowledge vault. Runs on the developer's machine, browsable in any browser.

## Architecture

```
Browser → Local Web Server (FastAPI) → MCP Client (StreamableHTTP) → Encyclist on Fly.io
```

- **No database** — reads everything from the remote Encyclist via MCP
- **Server-side rendering** — Jinja2 templates (fast, simple, SEO-like page structure)
- **Light styling** — Wikipedia-inspired, clean, readable

## Tech Stack

- **Python 3.11** — runs in the existing Encyclist venv
- **FastAPI** — web server (already a dependency)
- **Jinja2** — HTML templates (already bundled with FastAPI deps)
- **MCP Python SDK** — `mcp.client.streamable_http` for connecting to remote server
- **htmx** — lightweight interactivity (search suggestions, inline edits) via CDN
- **CSS** — single custom stylesheet, Wikipedia-inspired (no heavy framework)

## Pages & Routes

### 1. Home Page — `/`
- Search bar (prominent, centered)
- Quick stats: entity count, doc count, relationship count (from `ec_stats`)
- Recent activity: last 10 created/updated entities and docs
- Alphabetical index of entity types (from `ec_entity_type_list`)

### 2. Entity Page — `/entity/{entity_id}`
- **Title**: entity name or ID
- **Type badge**: entity type with icon
- **Properties table**: all key-value pairs from entity data
- **Relationships section**:
  - Outgoing: "This entity → [linked entity]" with clickable links
  - Incoming: "[Linked entity] → This entity" with clickable links
  - Loaded via `ec_rel_query` with depth=1 both directions
- **Documents section**: docs related to this entity (search by entity name)
- **Edit button**: opens inline editor (htmx) to update entity data
- **Delete button**: with confirmation

### 3. Entity Type Index — `/type/{type_name}`
- Lists all entities of that type (via `ec_entity_query` with type filter)
- Sortable table: name, created date, key fields
- "Create New" button for adding entities of this type

### 4. Document Page — `/doc/{doc_id}`
- **Title**: doc title
- **Tags**: clickable tag badges
- **Source**: if available
- **Content**: rendered as Markdown (use `markdown` library)
- **Related entities**: semantic search using doc content
- **Edit button**: textarea editor with markdown preview
- **Delete button**: with confirmation

### 5. Search — `/search?q=...`
- Unified search using `ec_search` (merges entity + doc results)
- Shows results grouped by type: Entities first, then Documents
- Each result is a clickable link to its detail page
- Instant search suggestions via htmx (debounced, `/search/suggest?q=...`)

### 6. Create Entity — `/create`
- Form: select entity type (dropdown from `ec_entity_type_list`)
- Dynamic form fields based on entity type schema
- Submit calls `ec_entity_create`

### 7. Create Document — `/doc/new`
- Form: title, tags (comma-separated), content (markdown textarea)
- Submit calls `ec_doc_add`

### 8. Relationships — `/relations`
- Visual list of recent relationships
- "Add Relationship" form: from_id, relation type, to_id (with autocomplete)
- Submit calls `ec_rel_add`

### 9. Graph Explorer — `/graph`
- Simple force-directed graph visualization (use D3.js via CDN or vis.js)
- Shows entities as nodes, relationships as edges
- Click node → navigate to entity page
- Filter by entity type
- Lightweight — only loads immediate neighborhood on click (lazy expansion)

## MCP Connection

The web server maintains a persistent MCP session:

```python
from mcp.client.streamable_http import streamablehttp_client

async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    # Connect, call tool, return result
    # Uses the configured endpoint URL and API key
```

Configuration via environment variables or a small `.env` file:
```
ENCYCLIST_URL=https://encyclist.fly.dev/mcp
ENCYCLIST_API_KEY=ec-...
```

For local dev, read from `.env`. The API key should NOT be hardcoded.

## File Structure

```
encyclist/
├── web/
│   ├── __init__.py
│   ├── app.py              # FastAPI app, routes, MCP client
│   ├── mcp_client.py       # MCP connection manager (pool/reconnect)
│   ├── templates/
│   │   ├── base.html        # Layout: header, nav, search bar, footer
│   │   ├── home.html        # Home page
│   │   ├── entity.html      # Entity detail page
│   │   ├── entity_edit.html # Entity edit form (htmx partial)
│   │   ├── type_index.html  # Entity type listing
│   │   ├── doc.html         # Document detail page
│   │   ├── doc_edit.html    # Document edit form
│   │   ├── doc_new.html     # New document form
│   │   ├── search.html      # Search results
│   │   ├── create.html      # Create entity form
│   │   ├── relations.html   # Relationships page
│   │   ├── graph.html       # Graph explorer
│   │   └── partials/
│   │       ├── search_suggest.html  # Search suggestions dropdown
│   │       ├── entity_card.html     # Entity card for listings
│   │       └── doc_card.html        # Doc card for listings
│   └── static/
│       ├── style.css        # Wikipedia-inspired stylesheet
│       └── graph.js         # D3/vis.js graph visualization
├── .env.example             # Template for local config
└── run_web.sh               # Simple launcher script
```

## Design Principles

1. **Wikipedia feel** — clean serif headings, blue links, subtle borders, info boxes
2. **Fast navigation** — pages load server-side, htmx for interactive bits only
3. **Read-first** — optimized for browsing and discovering content
4. **Lightweight** — no Node.js build step, no React, no heavy frameworks
5. **Markdown rendering** — document content renders as rich text
6. **Responsive** — works on mobile (friend might browse on phone)

## Running

```bash
cd ~/Projects/encyclist
source .venv/bin/activate
python -m web.app
# Opens http://localhost:8080
```

Or with the launcher:
```bash
./run_web.sh
```

## API Key

The `.env` file stores the API key (gitignored). For the local UI, use the "hermes" key since it's running on the same machine. The friend uses their own key when running their own instance.

## Future Enhancements (not in v1)
- Authentication (basic auth for the local web server)
- Real-time updates via SSE (when entities change)
- Export to static HTML (publish a snapshot)
- Dark mode toggle

# GameVault

Self-hosted, MCP-native knowledge base for game development collaboration.

Two storage engines, one MCP endpoint:
- **ChromaDB** — semantic search for design docs, PRDs, lore, brainstorms
- **SQLite** — structured queries for game entities (creatures, items, quests, locations)
- **Relationship graph** — links everything together

Agents are the primary interface. Humans interact through their agents.

## Setup
```bash
cd ~/Projects/gamevault
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Specs
See `specs/` folder for full design documentation.

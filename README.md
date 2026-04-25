# Encyclist

Self-hosted, MCP-native shared knowledge base. Two storage engines, one endpoint:

- **ChromaDB** — semantic search for docs, PRDs, notes, brainstorms
- **SQLite** — structured queries for tabular data (entities, stats, properties)
- **Relationship graph** — links everything together

Agents are the primary interface. Humans interact through their agents.

Deployed on Fly.io. Auto-wakes on traffic. API key auth for multi-agent access.

## Setup
```bash
cd ~/Projects/encyclist
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Specs
See `specs/` folder for full design documentation.

## Deployment
```bash
fly deploy
```

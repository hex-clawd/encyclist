# Encyclist — Deployment Spec (Fly.io)

## Overview

Encyclist deploys as a single Fly.io app. One Docker container, one persistent volume, one URL. Agents connect over HTTPS via MCP StreamableHTTP protocol.

## URL

`https://encyclist.fly.dev/mcp`

## Architecture on Fly

```
                        ┌─────────────────────┐
                        │   Fly.io Load Balancer │
                        │   (HTTPS termination)  │
                        └──────────┬────────────┘
                                   │
                        ┌──────────▼────────────┐
                        │  Encyclist Container  │
                        │  (Python, Uvicorn)    │
                        │                      │
                        │  MCP Server :8000    │
                        │  ├─ /mcp (StreamableHTTP) │
                        │  ├─ /health          │
                        │  └─ /                │ (optional web UI)
                        │                      │
                        │  /data (persistent volume)
                        │  ├─ encyclist.db     │
                        │  └─ chroma/          │
                        └──────────────────────┘
```

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src/ src/

# ChromaDB needs some local storage
ENV CHROMA_HOME=/data/chroma

EXPOSE 8000

CMD ["uvicorn", "src.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

## fly.toml

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
  [http_service.concurrency]
    type = "requests"
    soft_limit = 10

[mounts]
  source = "encyclist_data"
  destination = "/data"
  initial_size = "1gb"

[env]
  ENCYCLIST_DATA_DIR = "/data"
```

## First-time Setup

```bash
# Create the app
fly apps create encyclist

# Create persistent volume
fly volumes create encyclist_data --size 1 --region ams

# Set secrets (API keys, not in code)
fly secrets set ENCYCLIST_KEYS='[{"name":"hermes","key":"sk-ec-xxxx"},{"name":"designer","key":"sk-ec-yyyy"}]'

# Deploy
fly deploy

# Initialize (first run creates tables)
fly ssh console -a encyclist --command "python -m src.init"
```

## Resource Estimates

- **RAM:** 256MB (plenty for SQLite + small ChromaDB collection)
- **CPU:** shared-cpu-1x (this is not compute-heavy)
- **Disk:** 1GB persistent volume (holds ~10K entities + ~1K docs easily)
- **Cost:** within existing Fly plan (paid sub already covers this)

## Auto-wake Behavior

With `auto_stop_machines = true` and `min_machines_running = 0`:

1. Machine stops after ~5 minutes of no traffic
2. When an agent POSTs to `/mcp`, Fly wakes the machine
3. Cold start: ~2-5 seconds (Python app loading + ChromaDB init)
4. Subsequent requests are instant while machine is warm

This means zero cost when nobody's working, but a small delay on first request after idle.

## Authentication

API keys passed via `X-API-Key` header on every MCP request.

Keys are stored as SHA256 hashes in `ec_api_keys` table. The server never logs plaintext keys.

**Setup:** keys are defined in `ENCYCLIST_KEYS` env var (set via `fly secrets set`). On startup, server syncs these into the database.

## Monitoring

- `/health` endpoint returns `{"status": "ok"}` — for Fly health checks
- Fly dashboard shows request counts, latency, machine status
- `ec_stats` MCP tool gives a quick data overview

## Backup Strategy

1. **Export:** Agent runs `ec_export` periodically → saves JSON locally
2. **Fly volume snapshot:** automatic (Fly takes snapshots of persistent volumes)
3. **Manual:** `fly ssh console` → copy `/data/encyclist.db` and `/data/chroma/`

## Scaling (if ever needed)

Not needed for a single-project tool, but if it grows:

- Increase volume size: `fly volumes extend encyclist_data --size 5`
- Add machines in another region for redundancy
- Swap SQLite for Postgres (Supabase) if concurrent writes become an issue

## Connecting Agents

### Hermes (Matej's agent)
Add to `~/.hermes/config.yaml` under MCP servers:
```yaml
encyclist:
  transport: streamable-http
  url: https://encyclist.fly.dev/mcp
  headers:
    X-API-Key: sk-ec-xxxx
```

### Friend's Agent
Same pattern, different API key. Depends on their agent's MCP client config.

# Encyclist — Data Model

## SQLite Schema

### `ec_entity_types`
Defines the schema for each entity type. Created on-the-fly by users.

```sql
CREATE TABLE ec_entity_types (
    name        TEXT PRIMARY KEY,     -- "creatures", "items", "quests"
    description TEXT,                 -- Human-readable description
    fields      TEXT NOT NULL,        -- JSON: field definitions
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

`fields` JSON structure:
```json
{
  "name": {
    "type": "string",       // string|int|float|bool|text|json
    "required": true,
    "description": "Creature name"
  },
  "hp": {
    "type": "int",
    "required": true,
    "description": "Base hit points"
  }
}
```

### `ec_entities`
Stores all entity instances. Data stored as JSON, queried via `json_extract()`.

```sql
CREATE TABLE ec_entities (
    id          TEXT PRIMARY KEY,     -- ent_xxxxxxxx
    type        TEXT NOT NULL,        -- FK to ec_entity_types.name
    data        TEXT NOT NULL,        -- JSON: entity field values
    created_by  TEXT,                 -- API key identity
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (type) REFERENCES ec_entity_types(name)
);

CREATE INDEX idx_entities_type ON ec_entities(type);
```

**Why JSON column instead of dynamic tables:**
- Entity types defined at runtime — can't create tables on the fly reliably
- SQLite's `json_extract(data, '$.hp')` supports WHERE clauses and indexing
- Simpler schema — never needs migration
- Performance: hundreds to low thousands of entities is trivial for SQLite

**Querying:**
```sql
-- All fire creatures with HP > 100
SELECT * FROM ec_entities 
WHERE type = 'creatures' 
  AND json_extract(data, '$.element') = 'Fire'
  AND json_extract(data, '$.hp') > 100
ORDER BY json_extract(data, '$.hp') DESC;
```

### `ec_relationships`
Typed directed edges between entities and/or documents.

```sql
CREATE TABLE ec_relationships (
    id          TEXT PRIMARY KEY,     -- rel_xxxxxxxx
    from_id     TEXT NOT NULL,        -- Entity or doc ID
    relation    TEXT NOT NULL,        -- "drops", "requires", "happens_in"
    to_id       TEXT NOT NULL,        -- Entity or doc ID
    properties  TEXT,                 -- JSON: optional relationship data
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(from_id, relation, to_id)
);

CREATE INDEX idx_rels_from ON ec_relationships(from_id);
CREATE INDEX idx_rels_to ON ec_relationships(to_id);
CREATE INDEX idx_rels_relation ON ec_relationships(relation);
```

### `ec_docs`
Metadata for documents stored in ChromaDB. ChromaDB holds embeddings + content,
SQLite holds structured metadata for filtering.

```sql
CREATE TABLE ec_docs (
    id          TEXT PRIMARY KEY,     -- doc_xxxxxxxx (matches ChromaDB ID)
    title       TEXT,
    source      TEXT,                 -- "matej", "designer", "meeting"
    tags        TEXT,                 -- JSON array of strings
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

### `ec_changes` (audit log)
Tracks all changes for history and debugging.

```sql
CREATE TABLE ec_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,        -- "create", "update", "delete"
    target_type TEXT NOT NULL,        -- "entity", "doc", "relationship", "entity_type"
    target_id   TEXT NOT NULL,
    changes     TEXT,                 -- JSON: what changed
    author      TEXT,                 -- API key identity
    timestamp   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_changes_target ON ec_changes(target_type, target_id);
```

### `ec_api_keys`
API keys for agent authentication.

```sql
CREATE TABLE ec_api_keys (
    key_hash    TEXT PRIMARY KEY,     -- SHA256 of the API key
    name        TEXT NOT NULL,        -- "hermes", "designer-agent"
    created_at  TEXT DEFAULT (datetime('now')),
    last_used   TEXT
);
```

---

## ChromaDB Collections

### `encyclist_docs`
Single collection for all documents.

- **Documents:** raw text content
- **Metadatas:** `{title, source, tags_json, created_at}`
- **IDs:** matching SQLite `ec_docs.id`
- **Embedding function:** all-MiniLM-L6-v2 (runs locally in the container, no API call needed)

---

## ID Scheme

All IDs use a prefix + 8-char hex for readability:

- Entity IDs: `ent_` → `ent_a1b2c3d4`
- Doc IDs: `doc_` → `doc_e5f6g7h8`
- Relationship IDs: `rel_` → `rel_i9j0k1l2`

---

## Authentication

API key based. Each agent gets a unique key.

- Keys are passed as `X-API-Key` header on every request
- Server hashes the key (SHA256) and looks up in `ec_api_keys`
- The key's `name` is used as `created_by` / `author` in entity and audit records
- No sessions, no tokens, no OAuth — just keys

**Key management:**
- `ec_key_create(name)` → generates a key, stores the hash, returns the plaintext key once
- `ec_key_list()` → shows key names and last used timestamps
- `ec_key_revoke(name)` → removes a key

---

## Data Directory Structure (on Fly.io volume)

```
/data/
├── encyclist.db     # SQLite database (all structured data + doc metadata)
└── chroma/          # ChromaDB persistence directory
```

Both live on the Fly persistent volume. Backed up via `ec_export` to JSON.

---

## Data Flow Examples

### "Add Fire Imp creature"
```
1. Agent calls ec_entity_create(type="creatures", data={...})
2. Server validates data against ec_entity_types.fields
3. Server inserts into ec_entities with generated ID
4. Server logs change in ec_changes (author = API key name)
5. Returns {entity_id: "ent_a1b2c3d4", ...}
```

### "What's the design intent for fire creatures?"
```
1. Agent calls ec_doc_search(query="design intent fire creatures")
2. Server queries ChromaDB with embedding
3. Returns matching docs with similarity scores
```

### "Generate spawning code for Volcanic Caves"
```
1. Agent calls ec_entity_query(type="creatures", where={"location": "Volcanic Caves"})
2. Server: WHERE type='creatures' AND json_extract(data, '$.location') = 'Volcanic Caves'
3. Agent calls ec_rel_query(from_id=<each creature>, relation="drops")
4. Agent has full structured data to generate code
```

### "What items does the Volcanic Boss quest need?"
```
1. Agent calls ec_entity_query(type="quests", where={"name": "Volcanic Boss"})
2. Agent calls ec_rel_query(from_id=<quest_id>, relation="requires", depth=2)
3. Returns: quest → requires → ember_stone → dropped_by → fire_imp
```

---

## Backup & Recovery

- **Export:** `ec_export` → JSON file with all data
- **Volume snapshot:** Fly.io persistent volumes can be snapshotted
- **Restore:** `ec_import` from JSON, or replace volume from snapshot
- **Recommended:** cron `ec_export` to a local file periodically

# GameVault — Data Model

## SQLite Schema

### `gv_entity_types`
Defines the schema for each entity type. Created on-the-fly by designers.

```sql
CREATE TABLE gv_entity_types (
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

### `gv_entities`
Stores all entity instances. Entity data is stored as JSON in a single column.
Dynamic tables are NOT used — instead, we store JSON and query via SQLite's `json_extract()`.

```sql
CREATE TABLE gv_entities (
    id          TEXT PRIMARY KEY,     -- UUID
    type        TEXT NOT NULL,        -- FK to gv_entity_types.name
    data        TEXT NOT NULL,        -- JSON: entity field values
    created_by  TEXT,                 -- Agent/user who created this
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (type) REFERENCES gv_entity_types(name)
);

CREATE INDEX idx_entities_type ON gv_entities(type);
```

**Why JSON column instead of dynamic tables?**
- Entity types are defined at runtime by designers — we can't create tables on the fly reliably
- SQLite's `json_extract(data, '$.hp')` supports indexing and WHERE clauses
- Simpler migration story — schema never changes
- Performance: for a game project (hundreds to low thousands of entities), this is plenty fast

**Querying:**
```sql
-- All fire creatures with HP > 100
SELECT * FROM gv_entities 
WHERE type = 'creatures' 
  AND json_extract(data, '$.element') = 'Fire'
  AND json_extract(data, '$.hp') > 100
ORDER BY json_extract(data, '$.hp') DESC;
```

### `gv_relationships`
Typed directed edges between entities and/or documents.

```sql
CREATE TABLE gv_relationships (
    id          TEXT PRIMARY KEY,     -- UUID
    from_id     TEXT NOT NULL,        -- Entity or doc ID
    relation    TEXT NOT NULL,        -- "drops", "requires", "happens_in"
    to_id       TEXT NOT NULL,        -- Entity or doc ID
    properties  TEXT,                 -- JSON: optional relationship data
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(from_id, relation, to_id)
);

CREATE INDEX idx_rels_from ON gv_relationships(from_id);
CREATE INDEX idx_rels_to ON gv_relationships(to_id);
CREATE INDEX idx_rels_relation ON gv_relationships(relation);
```

### `gv_docs`
Metadata for documents stored in ChromaDB. ChromaDB holds the embeddings and content,
SQLite holds the structured metadata for filtering.

```sql
CREATE TABLE gv_docs (
    id          TEXT PRIMARY KEY,     -- UUID (matches ChromaDB ID)
    title       TEXT,
    source      TEXT,                 -- "matej", "designer", "meeting"
    tags        TEXT,                 -- JSON array of strings
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

### `gv_changes` (audit log)
Tracks all changes for history and conflict resolution.

```sql
CREATE TABLE gv_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,        -- "create", "update", "delete"
    target_type TEXT NOT NULL,        -- "entity", "doc", "relationship", "entity_type"
    target_id   TEXT NOT NULL,
    changes     TEXT,                 -- JSON: what changed
    author      TEXT,                 -- Agent/user who made the change
    timestamp   TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_changes_target ON gv_changes(target_type, target_id);
```

---

## ChromaDB Collections

### `gamevault_docs`
Single collection for all documents.

- **Documents:** the raw text content
- **Metadatas:** `{title, source, tags_json, created_at}`
- **IDs:** matching SQLite `gv_docs.id`
- **Embedding function:** default (all-MiniLM-L6-v2 or OpenAI, configurable)

No collections per project or tag — ChromaDB's metadata filtering handles that.

---

## ID Scheme

All IDs are UUIDs generated at creation time:

- Entity IDs: `ent_` prefix + short UUID → `ent_a1b2c3d4`
- Doc IDs: `doc_` prefix + short UUID → `doc_e5f6g7h8`
- Relationship IDs: `rel_` prefix + short UUID → `rel_i9j0k1l2`

Short UUIDs (8 chars) for readability in agent conversations. Collision probability negligible at game-project scale.

---

## Data Flow Examples

### "Add Fire Imp creature"
```
1. Agent calls gv_entity_create(type="creatures", data={...})
2. Server validates data against gv_entity_types.fields
3. Server inserts into gv_entities with generated ID
4. Server logs change in gv_changes
5. Returns {entity_id: "ent_a1b2c3d4", ...}
```

### "What's the design intent for fire creatures?"
```
1. Agent calls gv_doc_search(query="design intent fire creatures")
2. Server queries ChromaDB with embedding
3. Returns matching docs with similarity scores
```

### "Generate spawning code for Volcanic Caves"
```
1. Agent calls gv_entity_query(type="creatures", where={"location": "Volcanic Caves"})
2. Server runs SQL: WHERE type='creatures' AND json_extract(data, '$.location') = 'Volcanic Caves'
3. Agent calls gv_rel_query(from_id=<each creature>, relation="drops")
4. Agent has full structured data to generate code
```

### "What items does the Volcanic Boss quest require?"
```
1. Agent calls gv_entity_query(type="quests", where={"name": "Volcanic Boss"})
2. Agent calls gv_rel_query(from_id=<quest_id>, relation="requires", depth=2)
3. Returns: quest → requires → ember_stone (item) → dropped_by → fire_imp (creature)
4. Agent can tell the designer: "You need to kill Fire Imps for Ember Stones before starting this quest"
```

---

## Backup & Portability

The entire vault is two things:
1. `data/gamevault.db` — SQLite file (entities, relationships, doc metadata, audit log)
2. `data/chroma/` — ChromaDB directory (doc embeddings)

Back up by copying both. Restore by replacing both. Export to JSON via `gv_export` for human-readable snapshots or migration.

# Encyclist — MCP Tools Specification

All tools exposed via the Encyclist MCP server. Agents connect over StreamableHTTP at `https://encyclist.fly.dev/mcp`. Auth via `X-API-Key` header.

**Tool naming prefix:** `ec_` (for encyclist)

---

## Document Store Tools (ChromaDB-backed)

For unstructured content: design docs, PRDs, lore, meeting notes, brainstorms, random ideas. No organization required — indexed by meaning.

### `ec_doc_add`
Store a document. Content is indexed by meaning automatically.

**Parameters:**
- `content` (string, required) — the document text
- `title` (string, optional) — short title for display
- `tags` (string[], optional) — freeform tags for filtering
- `source` (string, optional) — who/what produced this ("matej", "designer", "meeting-notes")

**Returns:** `{"doc_id": "...", "status": "stored"}`

**Example:**
```
ec_doc_add(
  content="Combat philosophy: fire creatures are glass cannons — high damage, low HP. 
           This contrasts with earth creatures which are tanks. Ice creatures are 
           crowd-control specialists with moderate stats.",
  title="Combat Element Philosophy",
  tags=["combat", "design-intent", "elements"],
  source="designer"
)
```

---

### `ec_doc_search`
Semantic search across all documents. Finds by meaning, not keywords.

**Parameters:**
- `query` (string, required) — what to look for, natural language
- `tags` (string[], optional) — filter to docs with these tags
- `source` (string, optional) — filter to docs from this source
- `limit` (int, optional, default 5) — max results

**Returns:** Array of `{doc_id, title, content, tags, similarity, created_at}`

**Example:**
```
ec_doc_search(query="what's the design philosophy for fire creatures?")
→ Returns the "Combat Element Philosophy" doc
```

---

### `ec_doc_get`
Retrieve a specific document by ID.

**Parameters:**
- `doc_id` (string, required)

**Returns:** `{doc_id, title, content, tags, source, created_at, updated_at}`

---

### `ec_doc_update`
Update an existing document's content or metadata.

**Parameters:**
- `doc_id` (string, required)
- `content` (string, optional) — new content (replaces entirely)
- `title` (string, optional) — new title
- `tags` (string[], optional) — replace tags

**Returns:** `{"status": "updated", "doc_id": "..."}`

---

### `ec_doc_list`
List documents, optionally filtered.

**Parameters:**
- `tags` (string[], optional)
- `source` (string, optional)
- `limit` (int, optional, default 20)
- `offset` (int, optional, default 0)

**Returns:** `{total: N, docs: [{doc_id, title, tags, created_at}]}`

---

### `ec_doc_delete`
Remove a document.

**Parameters:**
- `doc_id` (string, required)

**Returns:** `{"status": "deleted"}`

---

## Entity Store Tools (SQLite-backed)

For structured tabular data: game entities, product catalogs, configuration tables, anything with defined fields. Entity types are created on-the-fly.

### `ec_entity_type_define`
Define a new entity type with its schema.

**Parameters:**
- `name` (string, required) — entity type name (e.g. "creatures", "items", "quests")
- `fields` (object, required) — field definitions
  - Each key is a field name, value is `{type: "string"|"int"|"float"|"bool"|"text"|"json", required: bool, description: string}`
- `description` (string, optional) — what this entity type represents

**Returns:** `{"type_name": "...", "fields": {...}, "status": "created"}`

**Example:**
```
ec_entity_type_define(
  name="creatures",
  fields={
    "name":        {"type": "string", "required": true, "description": "Creature name"},
    "hp":          {"type": "int",    "required": true, "description": "Base hit points"},
    "attack":      {"type": "int",    "required": true, "description": "Base attack power"},
    "element":     {"type": "string", "required": true, "description": "Fire/Ice/Earth/Arcane/Neutral"},
    "rarity":      {"type": "string", "required": true, "description": "Common/Uncommon/Rare/Legendary"},
    "description": {"type": "text",   "required": false, "description": "Lore/flavor text"},
    "drops":       {"type": "json",   "required": false, "description": "List of dropped items with chances"},
    "location":    {"type": "string", "required": false, "description": "Where this creature spawns"},
    "abilities":   {"type": "json",   "required": false, "description": "List of ability IDs"}
  },
  description="All hostile and friendly creatures in the game"
)
```

---

### `ec_entity_type_list`
List all defined entity types.

**Parameters:** none

**Returns:** `[{name, description, field_count, entity_count}]`

---

### `ec_entity_create`
Create a new entity instance.

**Parameters:**
- `type` (string, required) — entity type name
- `data` (object, required) — field values matching the type's schema

**Returns:** `{"entity_id": "...", "type": "...", "data": {...}}`

**Example:**
```
ec_entity_create(
  type="creatures",
  data={
    "name": "Fire Imp",
    "hp": 80,
    "attack": 45,
    "element": "Fire",
    "rarity": "Rare",
    "description": "A mischievous fire spirit that haunts volcanic caves.",
    "location": "Volcanic Caves",
    "drops": [{"item": "Ember Stone", "chance": 0.3}]
  }
)
```

---

### `ec_entity_get`
Get a single entity by ID.

**Parameters:**
- `entity_id` (string, required)

**Returns:** `{entity_id, type, data, created_at, updated_at, created_by}`

---

### `ec_entity_query`
Exact structured query. The precision tool for code generation and exact filtering.

**Parameters:**
- `type` (string, required) — entity type to query
- `where` (object, optional) — field filters
  - Supports: `{"field": value}` (exact), `{"field": {">": 100}}`, `{"field": {"in": ["a","b"]}}`
  - Operators: `=`, `!=`, `>`, `<`, `>=`, `<=`, `in`, `like`
- `order_by` (string, optional) — field to sort by
- `order_dir` (string, optional) — "asc" or "desc", default "asc"
- `limit` (int, optional, default 50)
- `offset` (int, optional, default 0)

**Returns:** `{total: N, entities: [{entity_id, data}]}`

**Examples:**
```
// All rare fire creatures with HP > 100
ec_entity_query(
  type="creatures",
  where={"element": "Fire", "rarity": "Rare", "hp": {">": 100}},
  order_by="hp",
  order_dir="desc"
)

// All creatures in Volcanic Caves, sorted by attack
ec_entity_query(
  type="creatures",
  where={"location": "Volcanic Caves"},
  order_by="attack",
  order_dir="desc"
)

// All entities of a type
ec_entity_query(type="creatures")
```

---

### `ec_entity_update`
Update entity field values. Partial update — only listed fields change.

**Parameters:**
- `entity_id` (string, required)
- `data` (object, required) — fields to update

**Returns:** `{"status": "updated", "entity_id": "...", "data": {...}}`

---

### `ec_entity_delete`
Delete an entity.

**Parameters:**
- `entity_id` (string, required)

**Returns:** `{"status": "deleted"}`

---

## Relationship Tools

### `ec_rel_add`
Create a typed directed relationship between two entities or between an entity and a document.

**Parameters:**
- `from_id` (string, required) — source entity/doc ID
- `relation` (string, required) — relationship type (e.g. "drops", "requires", "happens_in", "references")
- `to_id` (string, required) — target entity/doc ID
- `properties` (object, optional) — extra data on the relationship (e.g. {"chance": 0.3})

**Returns:** `{"rel_id": "...", "from": "...", "relation": "...", "to": "..."}`

**Examples:**
```
// Quest requires item
ec_rel_add(from_id="quest_001", relation="requires", to_id="item_sword_01")

// Creature drops item (with drop chance)
ec_rel_add(from_id="creature_fire_imp", relation="drops", to_id="item_ember_stone", 
           properties={"chance": 0.3})

// Entity references design doc
ec_rel_add(from_id="creature_fire_imp", relation="designed_by", to_id="doc_combat_philosophy")
```

---

### `ec_rel_query`
Find relationships. Supports multi-hop traversal.

**Parameters:**
- `from_id` (string, optional) — filter by source
- `to_id` (string, optional) — filter by target
- `relation` (string, optional) — filter by relationship type
- `depth` (int, optional, default 1) — traverse depth (1 = direct, 2 = two hops)

**Returns:** `{relationships: [{rel_id, from_id, relation, to_id, properties}]}`

**Examples:**
```
// What does the Fire Imp drop?
ec_rel_query(from_id="creature_fire_imp", relation="drops")

// Full chain: quest → requires → item → dropped_by → creature
ec_rel_query(from_id="quest_001", depth=2)
```

---

### `ec_rel_delete`
Remove a relationship.

**Parameters:**
- `rel_id` (string, required)

**Returns:** `{"status": "deleted"}`

---

## Utility Tools

### `ec_stats`
Overview of the vault — entity counts, doc counts, relationship counts.

**Parameters:** none

**Returns:** `{entities: {type_name: count}, documents: count, relationships: count, entity_types: [names]}`

---

### `ec_search`
Universal search — tries both semantic (docs) and structured (entities) and returns merged results. For when the agent doesn't know which store to hit.

**Parameters:**
- `query` (string, required) — natural language query
- `limit` (int, optional, default 10)

**Returns:** `{results: [{type: "doc"|"entity", id, summary, score}]}`

---

### `ec_export`
Export all data as JSON. For backup or migration.

**Parameters:** none

**Returns:** Full JSON dump of all entity types, entities, docs, relationships.

---

### `ec_import`
Import data from a JSON export. Merges with existing data.

**Parameters:**
- `data` (object, required) — the exported JSON structure

**Returns:** `{"imported": {entities: N, docs: N, relationships: N}}`

"""End-to-end integration test.

Exercises the full vault workflow against real backing stores (SQLite
+ ChromaDB) without going over HTTP — fast, deterministic, and proves
the pieces compose. Then writes a JSON export, builds a *second* vault
on a fresh tmp dir, imports the export, and verifies the data survives
the round-trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest


CREATURE_FIELDS = {
    "name":        {"type": "string", "required": True,  "description": "Creature name"},
    "hp":          {"type": "int",    "required": True,  "description": "Hit points"},
    "attack":      {"type": "int",    "required": True,  "description": "Attack power"},
    "element":     {"type": "string", "required": True,  "description": "Element"},
    "rarity":      {"type": "string", "required": True,  "description": "Rarity"},
    "description": {"type": "text",   "required": False, "description": "Lore"},
    "location":    {"type": "string", "required": False, "description": "Spawn location"},
}

ITEM_FIELDS = {
    "name":        {"type": "string", "required": True, "description": "Item name"},
    "rarity":      {"type": "string", "required": True, "description": "Rarity"},
    "description": {"type": "text",   "required": False, "description": "Flavor text"},
}


def _build_vault(root: Path):
    """Build a fresh (entity_store, doc_store, graph) trio rooted at `root`."""
    from src.db import connect, init_schema
    from src.doc_store import DocStore
    from src.entity_store import EntityStore
    from src.graph import Graph

    root.mkdir(parents=True, exist_ok=True)
    chroma_dir = root / "chroma"
    chroma_dir.mkdir(exist_ok=True)
    conn = connect(root / "encyclist.db")
    init_schema(conn)
    return EntityStore(conn), DocStore(conn, chroma_dir), Graph(conn), conn


def _export(entities, docs, graph) -> dict:
    """Mirror of `ec_export` against arbitrary store instances."""
    types = entities.list_types()
    out_entities: list[dict] = []
    for tdef in types:
        page = entities.query_entities(type_name=tdef["name"], limit=10**9)
        out_entities.extend(
            {
                "entity_id": e["entity_id"],
                "type": e["type"],
                "data": e["data"],
            }
            for e in page["entities"]
        )
    return {
        "version": 1,
        "entity_types": [
            {"name": t["name"], "description": t["description"], "fields": t["fields"]}
            for t in types
        ],
        "entities": out_entities,
        "docs": docs.all_docs(),
        "relationships": graph.all_edges(),
    }


def _import(data: dict, entities, docs, graph) -> dict:
    """Mirror of `ec_import` — entity IDs are reissued, docs/edges keep theirs."""
    counts = {"entity_types": 0, "entities": 0, "docs": 0, "relationships": 0}

    for tdef in data.get("entity_types", []) or []:
        entities.define_type(
            name=tdef["name"],
            fields=tdef["fields"],
            description=tdef.get("description"),
        )
        counts["entity_types"] += 1

    id_map: dict[str, str] = {}
    for ent in data.get("entities", []) or []:
        new = entities.create_entity(type_name=ent["type"], data=ent["data"])
        id_map[ent["entity_id"]] = new["entity_id"]
        counts["entities"] += 1

    for doc in data.get("docs", []) or []:
        docs.import_doc(
            doc_id=doc["doc_id"],
            content=doc["content"],
            title=doc.get("title"),
            tags=doc.get("tags") or [],
            source=doc.get("source"),
        )
        counts["docs"] += 1

    for rel in data.get("relationships", []) or []:
        graph.import_edge(
            rel_id=rel["rel_id"],
            from_id=id_map.get(rel["from_id"], rel["from_id"]),
            relation=rel["relation"],
            to_id=id_map.get(rel["to_id"], rel["to_id"]),
            properties=rel.get("properties"),
        )
        counts["relationships"] += 1

    return {"imported": counts, "id_map": id_map}


def test_full_vault_lifecycle(tmp_path: Path):
    entities, docs, graph, _ = _build_vault(tmp_path / "vault1")

    # 1. Define entity types.
    entities.define_type("creatures", CREATURE_FIELDS, description="Game creatures")
    entities.define_type("items", ITEM_FIELDS, description="Loot items")

    # 2. Create entities.
    fire_imp = entities.create_entity(
        "creatures",
        {
            "name": "Fire Imp",
            "hp": 80, "attack": 45,
            "element": "Fire", "rarity": "Rare",
            "description": "A mischievous fire spirit haunting volcanic caves.",
            "location": "Volcanic Caves",
        },
    )
    ice_golem = entities.create_entity(
        "creatures",
        {
            "name": "Ice Golem",
            "hp": 220, "attack": 30,
            "element": "Ice", "rarity": "Legendary",
            "description": "A hulking construct of living glacier.",
            "location": "Frostpeak",
        },
    )
    ember_stone = entities.create_entity(
        "items",
        {
            "name": "Ember Stone", "rarity": "Rare",
            "description": "A warm, glowing stone — quest material.",
        },
    )

    # 3. Add a design doc about combat philosophy.
    doc = docs.add(
        content=(
            "Combat philosophy: fire creatures are glass cannons — high damage, "
            "low HP. Ice creatures are crowd-control specialists with moderate "
            "stats. Earth creatures are tanks. Element identity drives stat "
            "distribution; players should feel the difference."
        ),
        title="Combat Element Philosophy",
        tags=["combat", "design-intent", "elements"],
        source="designer",
    )

    # 4. Semantic search finds the doc by meaning, not keywords.
    hits = docs.search(query="what's the design intent for fire creatures?", limit=5)
    assert any(h["doc_id"] == doc["doc_id"] for h in hits), \
        f"semantic search missed the design doc; got {[h['title'] for h in hits]}"

    # 5. Structured query: all Fire creatures.
    fires = entities.query_entities("creatures", where={"element": "Fire"})
    assert fires["total"] == 1
    assert fires["entities"][0]["data"]["name"] == "Fire Imp"

    # 6. Link entity → entity (Fire Imp drops Ember Stone).
    drop_edge = graph.add(
        from_id=fire_imp["entity_id"],
        relation="drops",
        to_id=ember_stone["entity_id"],
        properties={"chance": 0.3},
    )

    # 7. Link entity → doc (Fire Imp designed_by combat philosophy).
    designed_edge = graph.add(
        from_id=fire_imp["entity_id"],
        relation="designed_by",
        to_id=doc["doc_id"],
    )

    # 8. Multi-hop query from the Fire Imp.
    direct = graph.query(from_id=fire_imp["entity_id"], depth=1)
    assert {e["to_id"] for e in direct} == {ember_stone["entity_id"], doc["doc_id"]}

    # Add a second hop so depth=2 actually discovers something new.
    graph.add(
        from_id=ember_stone["entity_id"],
        relation="required_by",
        to_id="quest_lava_chalice",
    )
    two_hop = graph.query(from_id=fire_imp["entity_id"], depth=2)
    assert "quest_lava_chalice" in {e["to_id"] for e in two_hop}

    # 9. Export everything.
    snapshot = _export(entities, docs, graph)
    assert snapshot["version"] == 1
    assert {t["name"] for t in snapshot["entity_types"]} == {"creatures", "items"}
    assert len(snapshot["entities"]) == 3
    assert len(snapshot["docs"]) == 1
    assert len(snapshot["relationships"]) == 3

    # JSON-roundtrip the snapshot to prove it's wire-safe.
    import json
    blob = json.dumps(snapshot)
    snapshot = json.loads(blob)

    # 10. Import into a *fresh* vault on a separate tmp dir.
    e2, d2, g2, _ = _build_vault(tmp_path / "vault2")
    result = _import(snapshot, e2, d2, g2)
    assert result["imported"] == {
        "entity_types": 2, "entities": 3, "docs": 1, "relationships": 3,
    }

    # Data survived: entity types, entities, doc content, relationships.
    types_after = {t["name"]: t for t in e2.list_types()}
    assert types_after["creatures"]["entity_count"] == 2
    assert types_after["items"]["entity_count"] == 1

    fires_after = e2.query_entities("creatures", where={"element": "Fire"})
    assert fires_after["total"] == 1
    assert fires_after["entities"][0]["data"]["name"] == "Fire Imp"
    new_fire_imp_id = fires_after["entities"][0]["entity_id"]

    # Doc survived with searchable content.
    hits_after = d2.search(query="design philosophy for fire creatures", limit=5)
    assert any("Combat" in (h["title"] or "") for h in hits_after)

    # Relationships were rewritten with the new entity IDs.
    direct_after = g2.query(from_id=new_fire_imp_id, depth=1)
    targets = {e["to_id"] for e in direct_after}
    assert doc["doc_id"] in targets, "entity→doc edge lost in import"
    # The drops edge should now point at the *new* ember-stone ID.
    items_after = e2.query_entities("items")
    new_ember_id = next(
        e["entity_id"] for e in items_after["entities"]
        if e["data"]["name"] == "Ember Stone"
    )
    assert new_ember_id in targets, "entity→entity edge not rewired to new ID"

    # Multi-hop still works in the new vault.
    two_hop_after = g2.query(from_id=new_fire_imp_id, depth=2)
    assert "quest_lava_chalice" in {e["to_id"] for e in two_hop_after}

    # 11. Stats check on the imported vault.
    stats = {
        "entities": {t["name"]: t["entity_count"] for t in e2.list_types()},
        "entity_types": [t["name"] for t in e2.list_types()],
        "documents": d2.count(),
        "relationships": g2.count(),
    }
    assert stats == {
        "entities": {"creatures": 2, "items": 1},
        "entity_types": ["creatures", "items"],
        "documents": 1,
        "relationships": 3,
    }

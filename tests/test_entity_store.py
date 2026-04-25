"""Entity store: type definitions, CRUD, and the json_extract query DSL."""

from __future__ import annotations

import pytest

from src.entity_store import EntityStoreError


CREATURE_FIELDS = {
    "name":     {"type": "string", "required": True,  "description": "name"},
    "hp":       {"type": "int",    "required": True,  "description": "hp"},
    "element":  {"type": "string", "required": True,  "description": "element"},
    "rarity":   {"type": "string", "required": False, "description": "rarity"},
    "abilities":{"type": "json",   "required": False, "description": "abilities"},
}


def test_define_type_and_list(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS, description="Hostile creatures")
    types = entity_store.list_types()
    assert len(types) == 1
    assert types[0]["name"] == "creatures"
    assert types[0]["field_count"] == 5
    assert types[0]["entity_count"] == 0


def test_define_type_rejects_unknown_field_type(entity_store):
    with pytest.raises(EntityStoreError):
        entity_store.define_type("bogus", {"x": {"type": "uuid"}})


def test_create_validates_required_fields(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    with pytest.raises(EntityStoreError):
        entity_store.create_entity("creatures", {"name": "Imp"})  # missing hp/element


def test_create_validates_unknown_fields(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    with pytest.raises(EntityStoreError):
        entity_store.create_entity(
            "creatures",
            {"name": "Imp", "hp": 80, "element": "Fire", "wings": True},
        )


def test_crud_roundtrip(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    created = entity_store.create_entity(
        "creatures",
        {"name": "Fire Imp", "hp": 80, "element": "Fire", "rarity": "Rare"},
        created_by="test-agent",
    )
    eid = created["entity_id"]
    assert eid.startswith("ent_")

    fetched = entity_store.get_entity(eid)
    assert fetched["data"]["name"] == "Fire Imp"
    assert fetched["created_by"] == "test-agent"

    entity_store.update_entity(eid, {"hp": 120})
    fetched = entity_store.get_entity(eid)
    assert fetched["data"]["hp"] == 120
    assert fetched["data"]["element"] == "Fire"  # unchanged

    assert entity_store.delete_entity(eid) is True
    assert entity_store.get_entity(eid) is None


def test_query_exact_and_operators(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    for name, hp, element, rarity in [
        ("Fire Imp",   80,  "Fire", "Rare"),
        ("Magma Lord", 250, "Fire", "Legendary"),
        ("Frost Wolf", 140, "Ice",  "Rare"),
        ("Ember Pup",  40,  "Fire", "Common"),
    ]:
        entity_store.create_entity(
            "creatures",
            {"name": name, "hp": hp, "element": element, "rarity": rarity},
        )

    # exact equality
    out = entity_store.query_entities("creatures", where={"element": "Fire"})
    assert out["total"] == 3

    # > operator + ordering
    out = entity_store.query_entities(
        "creatures",
        where={"hp": {">": 100}},
        order_by="hp",
        order_dir="desc",
    )
    names = [e["data"]["name"] for e in out["entities"]]
    assert names == ["Magma Lord", "Frost Wolf"]

    # in operator
    out = entity_store.query_entities(
        "creatures",
        where={"rarity": {"in": ["Rare", "Legendary"]}},
    )
    assert out["total"] == 3

    # combined
    out = entity_store.query_entities(
        "creatures",
        where={"element": "Fire", "hp": {">=": 80}},
    )
    assert {e["data"]["name"] for e in out["entities"]} == {"Fire Imp", "Magma Lord"}


def test_query_rejects_unknown_field(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    with pytest.raises(EntityStoreError):
        entity_store.query_entities("creatures", where={"alignment": "evil"})


def test_query_rejects_unknown_operator(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    with pytest.raises(EntityStoreError):
        entity_store.query_entities("creatures", where={"hp": {"between": [1, 100]}})


def test_partial_update_does_not_drop_fields(entity_store):
    entity_store.define_type("creatures", CREATURE_FIELDS)
    e = entity_store.create_entity(
        "creatures",
        {"name": "X", "hp": 50, "element": "Fire", "abilities": ["fireball"]},
    )
    entity_store.update_entity(e["entity_id"], {"hp": 60})
    after = entity_store.get_entity(e["entity_id"])
    assert after["data"]["abilities"] == ["fireball"]
    assert after["data"]["hp"] == 60

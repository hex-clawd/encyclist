"""Relationship graph: add, query (with depth), delete, dedupe."""

from __future__ import annotations


def test_add_query_delete(graph):
    edge = graph.add("ent_a", "drops", "ent_b", properties={"chance": 0.3})
    assert edge["rel_id"].startswith("rel_")

    found = graph.query(from_id="ent_a", relation="drops")
    assert len(found) == 1
    assert found[0]["properties"] == {"chance": 0.3}

    assert graph.delete(edge["rel_id"]) is True
    assert graph.query(from_id="ent_a") == []


def test_dedupe_updates_properties(graph):
    e1 = graph.add("ent_a", "drops", "ent_b", properties={"chance": 0.3})
    e2 = graph.add("ent_a", "drops", "ent_b", properties={"chance": 0.5})
    assert e1["rel_id"] == e2["rel_id"]
    edges = graph.query(from_id="ent_a")
    assert edges[0]["properties"] == {"chance": 0.5}


def test_multi_hop_traversal(graph):
    # quest -requires-> item -dropped_by-> creature
    graph.add("quest_1", "requires", "item_1")
    graph.add("item_1", "dropped_by", "creature_1")
    graph.add("creature_1", "lives_in", "location_1")

    one = graph.query(from_id="quest_1", depth=1)
    assert {e["to_id"] for e in one} == {"item_1"}

    two = graph.query(from_id="quest_1", depth=2)
    assert {e["to_id"] for e in two} == {"item_1", "creature_1"}

    three = graph.query(from_id="quest_1", depth=3)
    assert {e["to_id"] for e in three} == {"item_1", "creature_1", "location_1"}


def test_query_filters(graph):
    graph.add("ent_a", "drops", "ent_b")
    graph.add("ent_a", "knows", "ent_c")
    graph.add("ent_x", "drops", "ent_b")

    drops = graph.query(relation="drops")
    assert len(drops) == 2

    into_b = graph.query(to_id="ent_b")
    assert len(into_b) == 2

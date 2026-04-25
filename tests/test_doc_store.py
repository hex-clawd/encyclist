"""Doc store tests. ChromaDB is heavy to spin up — this module gets a
single store fixture and reuses it across tests."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def doc_store(tmp_path_factory):
    """Module-scoped doc store backed by a real ChromaDB persistent client."""
    from src.db import connect, init_schema
    from src.doc_store import DocStore

    tmp = tmp_path_factory.mktemp("doc_store")
    conn = connect(tmp / "encyclist.db")
    init_schema(conn)
    chroma_dir = tmp / "chroma"
    chroma_dir.mkdir()
    return DocStore(conn, chroma_dir)


def test_add_and_get(doc_store):
    out = doc_store.add(
        content="Fire creatures are glass cannons — high damage, low HP.",
        title="Combat Element Philosophy",
        tags=["combat", "design"],
        source="designer",
    )
    assert out["doc_id"].startswith("doc_")

    fetched = doc_store.get(out["doc_id"])
    assert fetched["title"] == "Combat Element Philosophy"
    assert fetched["tags"] == ["combat", "design"]
    assert fetched["source"] == "designer"


def test_search_finds_by_meaning(doc_store):
    doc_store.add(
        content="Ice creatures are crowd-control specialists.",
        title="Ice CC",
        tags=["combat"],
    )
    results = doc_store.search(query="crowd control creatures", limit=3)
    titles = [r["title"] for r in results]
    assert "Ice CC" in titles


def test_list_filters_by_tags(doc_store):
    doc_store.add(content="Lore about dragons", title="Dragon Lore", tags=["lore"])
    out = doc_store.list(tags=["lore"], limit=10)
    titles = [d["title"] for d in out["docs"]]
    assert "Dragon Lore" in titles


def test_update_and_delete(doc_store):
    out = doc_store.add(content="A short note", title="Note 1")
    doc_id = out["doc_id"]
    doc_store.update(doc_id, content="A longer, edited note", title="Note 1 v2")
    fetched = doc_store.get(doc_id)
    assert fetched["title"] == "Note 1 v2"
    assert "edited" in fetched["content"]

    assert doc_store.delete(doc_id) is True
    assert doc_store.get(doc_id) is None

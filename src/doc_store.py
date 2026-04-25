"""Semantic document store backed by ChromaDB.

ChromaDB owns the embeddings and content; SQLite (`ec_docs`) holds a
mirror of the metadata so we can list/filter cheaply without
round-tripping the vector DB. IDs are generated here and shared between
both stores.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional

import chromadb


class DocStoreError(ValueError):
    pass


def _gen_id() -> str:
    return f"doc_{secrets.token_hex(4)}"


class DocStore:
    def __init__(self, conn: sqlite3.Connection, chroma_dir: Path) -> None:
        self._conn = conn
        # PersistentClient is the supported way to persist a ChromaDB
        # collection to disk in v0.5+.
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection = self._client.get_or_create_collection(
            name="encyclist_docs"
        )

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(
        self,
        content: str,
        title: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
    ) -> dict:
        if not content or not content.strip():
            raise DocStoreError("`content` is required")
        doc_id = _gen_id()
        tags = list(tags or [])
        metadata = _build_metadata(title=title, source=source, tags=tags)

        self._collection.add(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata],
        )
        self._conn.execute(
            """
            INSERT INTO ec_docs(id, title, source, tags) VALUES (?, ?, ?, ?)
            """,
            (doc_id, title, source, json.dumps(tags)),
        )
        return {"doc_id": doc_id, "status": "stored"}

    def update(
        self,
        doc_id: str,
        content: Optional[str] = None,
        title: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        existing = self.get(doc_id)
        if existing is None:
            raise DocStoreError(f"Document not found: {doc_id!r}")

        new_title = title if title is not None else existing["title"]
        new_tags = tags if tags is not None else existing["tags"]
        new_source = existing["source"]
        metadata = _build_metadata(
            title=new_title, source=new_source, tags=new_tags
        )

        update_kwargs: dict[str, Any] = {
            "ids": [doc_id],
            "metadatas": [metadata],
        }
        if content is not None:
            update_kwargs["documents"] = [content]
        self._collection.update(**update_kwargs)

        self._conn.execute(
            """
            UPDATE ec_docs
               SET title = ?, tags = ?, updated_at = datetime('now')
             WHERE id = ?
            """,
            (new_title, json.dumps(new_tags), doc_id),
        )
        return {"status": "updated", "doc_id": doc_id}

    def delete(self, doc_id: str) -> bool:
        existing = self.get(doc_id)
        if existing is None:
            return False
        self._collection.delete(ids=[doc_id])
        self._conn.execute("DELETE FROM ec_docs WHERE id = ?", (doc_id,))
        return True

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get(self, doc_id: str) -> Optional[dict]:
        result = self._collection.get(ids=[doc_id])
        if not result.get("ids"):
            return None
        meta = (result.get("metadatas") or [{}])[0] or {}
        content = (result.get("documents") or [""])[0]

        cur = self._conn.execute(
            "SELECT title, source, tags, created_at, updated_at FROM ec_docs WHERE id = ?",
            (doc_id,),
        )
        row = cur.fetchone()
        if row is None:
            # Out-of-band repair: ChromaDB has it, SQLite doesn't.
            tags = _decode_tags(meta.get("tags_json"))
            return {
                "doc_id": doc_id,
                "title": meta.get("title"),
                "content": content,
                "tags": tags,
                "source": meta.get("source"),
                "created_at": None,
                "updated_at": None,
            }
        return {
            "doc_id": doc_id,
            "title": row["title"],
            "content": content,
            "tags": json.loads(row["tags"] or "[]"),
            "source": row["source"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def search(
        self,
        query: str,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
        limit: int = 5,
    ) -> list[dict]:
        if not query or not query.strip():
            raise DocStoreError("`query` is required")
        # Chroma supports `where` on metadata; we built `tags` into a
        # JSON string so only `source` is filterable directly. Tag
        # filtering happens in Python after the vector search.
        where = {"source": source} if source else None
        result = self._collection.query(
            query_texts=[query],
            n_results=max(limit * 4, limit) if tags else limit,
            where=where,
        )

        ids = (result.get("ids") or [[]])[0]
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]

        # Pull SQLite metadata in one query for richer fields.
        sql_meta = self._fetch_meta_batch(ids)

        out: list[dict] = []
        for doc_id, content, meta, dist in zip(ids, docs, metas, dists):
            sql_row = sql_meta.get(doc_id, {})
            doc_tags = sql_row.get("tags") or _decode_tags(meta.get("tags_json") if meta else None)
            if tags and not set(tags).issubset(set(doc_tags or [])):
                continue
            similarity = _distance_to_similarity(dist)
            out.append(
                {
                    "doc_id": doc_id,
                    "title": sql_row.get("title") or (meta or {}).get("title"),
                    "content": content,
                    "tags": doc_tags,
                    "source": sql_row.get("source") or (meta or {}).get("source"),
                    "similarity": similarity,
                    "created_at": sql_row.get("created_at"),
                }
            )
            if len(out) >= limit:
                break
        return out

    def list(
        self,
        tags: Optional[list[str]] = None,
        source: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        clauses: list[str] = []
        params: list[Any] = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        # We over-fetch when filtering by tags so we can post-filter.
        fetch_limit = max(limit * 4, limit) if tags else limit
        total = self._conn.execute(
            f"SELECT COUNT(*) FROM ec_docs{where_sql}", params
        ).fetchone()[0]

        cur = self._conn.execute(
            f"""
            SELECT id, title, source, tags, created_at
              FROM ec_docs
              {where_sql}
             ORDER BY created_at DESC
             LIMIT ? OFFSET ?
            """,
            params + [int(fetch_limit), int(offset)],
        )

        docs: list[dict] = []
        for row in cur.fetchall():
            row_tags = json.loads(row["tags"] or "[]")
            if tags and not set(tags).issubset(set(row_tags)):
                continue
            docs.append(
                {
                    "doc_id": row["id"],
                    "title": row["title"],
                    "tags": row_tags,
                    "source": row["source"],
                    "created_at": row["created_at"],
                }
            )
            if len(docs) >= limit:
                break
        return {"total": total, "docs": docs}

    # ------------------------------------------------------------------
    # Internals / helpers used by import/export
    # ------------------------------------------------------------------

    def _fetch_meta_batch(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        cur = self._conn.execute(
            f"""
            SELECT id, title, source, tags, created_at
              FROM ec_docs
             WHERE id IN ({placeholders})
            """,
            ids,
        )
        return {
            row["id"]: {
                "title": row["title"],
                "source": row["source"],
                "tags": json.loads(row["tags"] or "[]"),
                "created_at": row["created_at"],
            }
            for row in cur.fetchall()
        }

    def all_docs(self) -> list[dict]:
        """Return every document with content. Used by ec_export."""
        result = self._collection.get()
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        sql_meta = self._fetch_meta_batch(ids)
        out: list[dict] = []
        for doc_id, content in zip(ids, docs):
            meta = sql_meta.get(doc_id, {})
            out.append(
                {
                    "doc_id": doc_id,
                    "title": meta.get("title"),
                    "content": content,
                    "tags": meta.get("tags") or [],
                    "source": meta.get("source"),
                    "created_at": meta.get("created_at"),
                }
            )
        return out

    def import_doc(
        self,
        doc_id: str,
        content: str,
        title: Optional[str],
        tags: Optional[list[str]],
        source: Optional[str],
    ) -> None:
        """Insert a doc with a known ID (used by ec_import)."""
        tags = list(tags or [])
        metadata = _build_metadata(title=title, source=source, tags=tags)
        # ChromaDB upsert
        self._collection.upsert(
            ids=[doc_id],
            documents=[content],
            metadatas=[metadata],
        )
        self._conn.execute(
            """
            INSERT INTO ec_docs(id, title, source, tags)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                source = excluded.source,
                tags = excluded.tags,
                updated_at = datetime('now')
            """,
            (doc_id, title, source, json.dumps(tags)),
        )

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM ec_docs").fetchone()[0]


def _build_metadata(
    *,
    title: Optional[str],
    source: Optional[str],
    tags: list[str],
) -> dict[str, Any]:
    """Chroma metadata values must be primitives — encode tags as JSON."""
    meta: dict[str, Any] = {}
    if title is not None:
        meta["title"] = title
    if source is not None:
        meta["source"] = source
    if tags:
        meta["tags_json"] = json.dumps(tags)
    if not meta:
        # Chroma rejects empty metadata; give it a stable marker.
        meta["_empty"] = True
    return meta


def _decode_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _distance_to_similarity(distance: Optional[float]) -> Optional[float]:
    if distance is None:
        return None
    # Chroma's default cosine distance ranges 0..2; map to 1..-1 similarity,
    # then clip to [0, 1] for the common case.
    sim = 1.0 - float(distance)
    if sim < 0:
        sim = 0.0
    if sim > 1:
        sim = 1.0
    return round(sim, 4)

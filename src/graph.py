"""Typed-edge relationship graph stored in `ec_relationships`.

Edges are directed and may connect any two IDs (entities or docs).
Multi-hop traversal in `query` walks edges by following `to_id` of one
hop into the `from_id` of the next; depth caps the chain length.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Optional


class GraphError(ValueError):
    pass


def _gen_id() -> str:
    return f"rel_{secrets.token_hex(4)}"


class Graph:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self,
        from_id: str,
        relation: str,
        to_id: str,
        properties: Optional[dict] = None,
    ) -> dict:
        if not from_id or not relation or not to_id:
            raise GraphError("`from_id`, `relation`, `to_id` are all required")
        rel_id = _gen_id()
        props_json = json.dumps(properties) if properties else None
        try:
            self._conn.execute(
                """
                INSERT INTO ec_relationships(id, from_id, relation, to_id, properties)
                VALUES (?, ?, ?, ?, ?)
                """,
                (rel_id, from_id, relation, to_id, props_json),
            )
        except sqlite3.IntegrityError:
            cur = self._conn.execute(
                """
                SELECT id FROM ec_relationships
                 WHERE from_id = ? AND relation = ? AND to_id = ?
                """,
                (from_id, relation, to_id),
            )
            row = cur.fetchone()
            if row is None:
                raise
            # Update properties on the existing edge.
            self._conn.execute(
                "UPDATE ec_relationships SET properties = ? WHERE id = ?",
                (props_json, row["id"]),
            )
            rel_id = row["id"]
        return {
            "rel_id": rel_id,
            "from_id": from_id,
            "relation": relation,
            "to_id": to_id,
            "properties": properties or {},
        }

    def query(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        relation: Optional[str] = None,
        depth: int = 1,
    ) -> list[dict]:
        depth = max(1, int(depth or 1))
        seen_edges: set[str] = set()
        results: list[dict] = []

        # First hop honours all three filters.
        first_hop = self._fetch(
            from_id=from_id, to_id=to_id, relation=relation
        )
        for edge in first_hop:
            if edge["rel_id"] in seen_edges:
                continue
            seen_edges.add(edge["rel_id"])
            results.append(edge)

        # Subsequent hops follow `to_id` outwards (no `to_id`/`relation`
        # filter — those constrained the starting set, not traversal).
        frontier = [edge["to_id"] for edge in first_hop]
        for _ in range(depth - 1):
            next_frontier: list[str] = []
            for node in frontier:
                hop = self._fetch(from_id=node)
                for edge in hop:
                    if edge["rel_id"] in seen_edges:
                        continue
                    seen_edges.add(edge["rel_id"])
                    results.append(edge)
                    next_frontier.append(edge["to_id"])
            frontier = next_frontier
            if not frontier:
                break
        return results

    def delete(self, rel_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM ec_relationships WHERE id = ?", (rel_id,)
        )
        return cur.rowcount > 0

    def count(self) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM ec_relationships"
        ).fetchone()[0]

    def all_edges(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT id, from_id, relation, to_id, properties, created_at
              FROM ec_relationships
            """
        )
        return [
            {
                "rel_id": row["id"],
                "from_id": row["from_id"],
                "relation": row["relation"],
                "to_id": row["to_id"],
                "properties": json.loads(row["properties"]) if row["properties"] else {},
                "created_at": row["created_at"],
            }
            for row in cur.fetchall()
        ]

    def import_edge(
        self,
        rel_id: str,
        from_id: str,
        relation: str,
        to_id: str,
        properties: Optional[dict] = None,
    ) -> None:
        props_json = json.dumps(properties) if properties else None
        self._conn.execute(
            """
            INSERT INTO ec_relationships(id, from_id, relation, to_id, properties)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(from_id, relation, to_id) DO UPDATE SET
                properties = excluded.properties
            """,
            (rel_id, from_id, relation, to_id, props_json),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _fetch(
        self,
        from_id: Optional[str] = None,
        to_id: Optional[str] = None,
        relation: Optional[str] = None,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list[Any] = []
        if from_id:
            clauses.append("from_id = ?")
            params.append(from_id)
        if to_id:
            clauses.append("to_id = ?")
            params.append(to_id)
        if relation:
            clauses.append("relation = ?")
            params.append(relation)
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        cur = self._conn.execute(
            f"""
            SELECT id, from_id, relation, to_id, properties
              FROM ec_relationships
              {where_sql}
            """,
            params,
        )
        return [
            {
                "rel_id": row["id"],
                "from_id": row["from_id"],
                "relation": row["relation"],
                "to_id": row["to_id"],
                "properties": json.loads(row["properties"]) if row["properties"] else {},
            }
            for row in cur.fetchall()
        ]

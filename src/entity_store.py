"""Structured-data entity store, backed by SQLite.

Entity types are declared at runtime; instances live in `ec_entities`
as JSON blobs and are queried via `json_extract`. The query DSL maps a
small `where` dict onto safe parameterised SQL — no string interpolation
on user input, only column names that we control.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from typing import Any, Optional

VALID_FIELD_TYPES = {"string", "int", "float", "bool", "text", "json"}
VALID_OPS = {"=", "!=", ">", "<", ">=", "<=", "in", "like"}


class EntityStoreError(ValueError):
    """Raised on validation or lookup failures the user can fix."""


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(4)}"


def _validate_field_name(name: str) -> str:
    if not name or not all(c.isalnum() or c == "_" for c in name):
        raise EntityStoreError(f"Invalid field name: {name!r}")
    return name


class EntityStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ------------------------------------------------------------------
    # Entity type definitions
    # ------------------------------------------------------------------

    def define_type(
        self,
        name: str,
        fields: dict[str, dict],
        description: Optional[str] = None,
    ) -> dict:
        if not name or not name.replace("_", "").isalnum():
            raise EntityStoreError(f"Invalid entity type name: {name!r}")
        if not isinstance(fields, dict) or not fields:
            raise EntityStoreError("`fields` must be a non-empty object")

        normalized: dict[str, dict] = {}
        for fname, spec in fields.items():
            _validate_field_name(fname)
            if not isinstance(spec, dict):
                raise EntityStoreError(f"Field {fname!r} spec must be an object")
            ftype = spec.get("type")
            if ftype not in VALID_FIELD_TYPES:
                raise EntityStoreError(
                    f"Field {fname!r} has unknown type {ftype!r}; "
                    f"allowed: {sorted(VALID_FIELD_TYPES)}"
                )
            normalized[fname] = {
                "type": ftype,
                "required": bool(spec.get("required", False)),
                "description": spec.get("description", ""),
            }

        fields_json = json.dumps(normalized)
        self._conn.execute(
            """
            INSERT INTO ec_entity_types(name, description, fields)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description = excluded.description,
                fields = excluded.fields,
                updated_at = datetime('now')
            """,
            (name, description, fields_json),
        )
        return {
            "type_name": name,
            "fields": normalized,
            "description": description,
            "status": "created",
        }

    def list_types(self) -> list[dict]:
        cur = self._conn.execute(
            """
            SELECT t.name, t.description, t.fields,
                   (SELECT COUNT(*) FROM ec_entities e WHERE e.type = t.name) AS entity_count
            FROM ec_entity_types t
            ORDER BY t.name
            """
        )
        out: list[dict] = []
        for row in cur.fetchall():
            fields = json.loads(row["fields"])
            out.append(
                {
                    "name": row["name"],
                    "description": row["description"],
                    "field_count": len(fields),
                    "entity_count": row["entity_count"],
                    "fields": fields,
                }
            )
        return out

    def get_type(self, name: str) -> Optional[dict]:
        cur = self._conn.execute(
            "SELECT name, description, fields FROM ec_entity_types WHERE name = ?",
            (name,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "name": row["name"],
            "description": row["description"],
            "fields": json.loads(row["fields"]),
        }

    # ------------------------------------------------------------------
    # Entity validation
    # ------------------------------------------------------------------

    def _validate_data(self, type_def: dict, data: dict, partial: bool) -> dict:
        if not isinstance(data, dict):
            raise EntityStoreError("`data` must be an object")
        fields = type_def["fields"]
        unknown = set(data) - set(fields)
        if unknown:
            raise EntityStoreError(
                f"Unknown fields for type {type_def['name']!r}: {sorted(unknown)}"
            )
        if not partial:
            missing = [
                f for f, spec in fields.items()
                if spec.get("required") and f not in data
            ]
            if missing:
                raise EntityStoreError(
                    f"Missing required fields: {missing}"
                )

        out: dict[str, Any] = {}
        for fname, value in data.items():
            spec = fields[fname]
            out[fname] = _coerce(spec["type"], fname, value)
        return out

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_entity(
        self,
        type_name: str,
        data: dict,
        created_by: Optional[str] = None,
    ) -> dict:
        type_def = self.get_type(type_name)
        if type_def is None:
            raise EntityStoreError(f"Unknown entity type: {type_name!r}")
        clean = self._validate_data(type_def, data, partial=False)
        entity_id = _gen_id("ent")
        self._conn.execute(
            "INSERT INTO ec_entities(id, type, data, created_by) VALUES (?, ?, ?, ?)",
            (entity_id, type_name, json.dumps(clean), created_by),
        )
        return {"entity_id": entity_id, "type": type_name, "data": clean}

    def get_entity(self, entity_id: str) -> Optional[dict]:
        cur = self._conn.execute(
            """
            SELECT id, type, data, created_by, created_at, updated_at
            FROM ec_entities WHERE id = ?
            """,
            (entity_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return {
            "entity_id": row["id"],
            "type": row["type"],
            "data": json.loads(row["data"]),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def update_entity(
        self,
        entity_id: str,
        data: dict,
    ) -> dict:
        existing = self.get_entity(entity_id)
        if existing is None:
            raise EntityStoreError(f"Entity not found: {entity_id!r}")
        type_def = self.get_type(existing["type"])
        if type_def is None:  # type was dropped — shouldn't normally happen
            raise EntityStoreError(
                f"Entity type {existing['type']!r} no longer exists"
            )
        patch = self._validate_data(type_def, data, partial=True)
        merged = {**existing["data"], **patch}
        self._conn.execute(
            """
            UPDATE ec_entities
               SET data = ?, updated_at = datetime('now')
             WHERE id = ?
            """,
            (json.dumps(merged), entity_id),
        )
        return {"status": "updated", "entity_id": entity_id, "data": merged}

    def delete_entity(self, entity_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM ec_entities WHERE id = ?", (entity_id,)
        )
        return cur.rowcount > 0

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query_entities(
        self,
        type_name: str,
        where: Optional[dict] = None,
        order_by: Optional[str] = None,
        order_dir: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        type_def = self.get_type(type_name)
        if type_def is None:
            raise EntityStoreError(f"Unknown entity type: {type_name!r}")

        valid_fields = set(type_def["fields"])
        clauses: list[str] = ["type = ?"]
        params: list[Any] = [type_name]

        for field, condition in (where or {}).items():
            if field not in valid_fields:
                raise EntityStoreError(
                    f"Unknown field {field!r} for type {type_name!r}"
                )
            _validate_field_name(field)
            extract = f"json_extract(data, '$.{field}')"
            if isinstance(condition, dict):
                if len(condition) != 1:
                    raise EntityStoreError(
                        f"Field {field!r} condition must have exactly one operator"
                    )
                (op, value), = condition.items()
                if op not in VALID_OPS:
                    raise EntityStoreError(
                        f"Unsupported operator {op!r}; allowed: {sorted(VALID_OPS)}"
                    )
                if op == "in":
                    if not isinstance(value, list) or not value:
                        raise EntityStoreError(
                            f"`in` operator requires a non-empty list"
                        )
                    placeholders = ",".join(["?"] * len(value))
                    clauses.append(f"{extract} IN ({placeholders})")
                    params.extend(value)
                elif op == "like":
                    clauses.append(f"{extract} LIKE ?")
                    params.append(value)
                else:
                    clauses.append(f"{extract} {op} ?")
                    params.append(value)
            else:
                clauses.append(f"{extract} = ?")
                params.append(condition)

        order_sql = ""
        if order_by is not None:
            if order_by not in valid_fields:
                raise EntityStoreError(
                    f"Unknown order_by field {order_by!r}"
                )
            _validate_field_name(order_by)
            direction = "DESC" if (order_dir or "asc").lower() == "desc" else "ASC"
            order_sql = f" ORDER BY json_extract(data, '$.{order_by}') {direction}"

        where_sql = " AND ".join(clauses)

        total = self._conn.execute(
            f"SELECT COUNT(*) FROM ec_entities WHERE {where_sql}",
            params,
        ).fetchone()[0]

        cur = self._conn.execute(
            f"""
            SELECT id, type, data, created_at, updated_at
              FROM ec_entities
             WHERE {where_sql}
             {order_sql}
             LIMIT ? OFFSET ?
            """,
            params + [int(limit), int(offset)],
        )
        entities = [
            {
                "entity_id": row["id"],
                "type": row["type"],
                "data": json.loads(row["data"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
            for row in cur.fetchall()
        ]
        return {"total": total, "entities": entities}

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def log_change(
        self,
        action: str,
        target_type: str,
        target_id: str,
        changes: Optional[dict] = None,
        author: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO ec_changes(action, target_type, target_id, changes, author)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                action,
                target_type,
                target_id,
                json.dumps(changes) if changes is not None else None,
                author,
            ),
        )


def _coerce(ftype: str, fname: str, value: Any) -> Any:
    """Light coercion / type-checking. We don't try to be clever — agents
    pass JSON-typed values; we just enforce the obvious mismatches."""
    if value is None:
        return None
    if ftype in ("string", "text"):
        if not isinstance(value, str):
            raise EntityStoreError(f"Field {fname!r} must be a string")
        return value
    if ftype == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise EntityStoreError(f"Field {fname!r} must be an int")
        return value
    if ftype == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise EntityStoreError(f"Field {fname!r} must be a number")
        return float(value)
    if ftype == "bool":
        if not isinstance(value, bool):
            raise EntityStoreError(f"Field {fname!r} must be a bool")
        return value
    if ftype == "json":
        # any JSON-serializable value is acceptable
        try:
            json.dumps(value)
        except (TypeError, ValueError) as e:
            raise EntityStoreError(
                f"Field {fname!r} must be JSON-serializable: {e}"
            ) from e
        return value
    raise EntityStoreError(f"Unknown field type {ftype!r}")

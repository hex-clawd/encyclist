"""SQLite connection + schema bootstrap.

All structured tables (entity types, entities, relationships, doc
metadata, audit log, api keys) live in a single SQLite file under the
data dir. We use `json_extract` for entity queries, so we need json1
which is bundled with stock SQLite on every supported Python build.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS ec_entity_types (
    name        TEXT PRIMARY KEY,
    description TEXT,
    fields      TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ec_entities (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    data        TEXT NOT NULL,
    created_by  TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (type) REFERENCES ec_entity_types(name)
);
CREATE INDEX IF NOT EXISTS idx_entities_type ON ec_entities(type);

CREATE TABLE IF NOT EXISTS ec_relationships (
    id          TEXT PRIMARY KEY,
    from_id     TEXT NOT NULL,
    relation    TEXT NOT NULL,
    to_id       TEXT NOT NULL,
    properties  TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(from_id, relation, to_id)
);
CREATE INDEX IF NOT EXISTS idx_rels_from ON ec_relationships(from_id);
CREATE INDEX IF NOT EXISTS idx_rels_to ON ec_relationships(to_id);
CREATE INDEX IF NOT EXISTS idx_rels_relation ON ec_relationships(relation);

CREATE TABLE IF NOT EXISTS ec_docs (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    source      TEXT,
    tags        TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ec_changes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    changes     TEXT,
    author      TEXT,
    timestamp   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_changes_target ON ec_changes(target_type, target_id);

CREATE TABLE IF NOT EXISTS ec_api_keys (
    key_hash    TEXT PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    created_at  TEXT DEFAULT (datetime('now')),
    last_used   TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection tuned for our access pattern."""
    conn = sqlite3.connect(
        str(db_path),
        check_same_thread=False,
        isolation_level=None,  # autocommit; explicit txns where needed
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)

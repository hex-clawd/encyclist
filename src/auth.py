"""API-key authentication for Encyclist.

Plaintext keys are never stored — only SHA256 hashes live in the
`ec_api_keys` table. Keys are passed via the `X-API-Key` HTTP header
and bound to the active request via a contextvar so MCP tools can read
the caller's name without plumbing it through every signature.
"""

from __future__ import annotations

import contextvars
import hashlib
import secrets
import sqlite3
from typing import Optional

current_api_key_name: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "encyclist_api_key_name", default=None
)


def hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_key() -> str:
    """Generate a fresh `sk-ec-...` API key (32 hex chars of entropy)."""
    return f"sk-ec-{secrets.token_hex(16)}"


class APIKeyAuth:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ---- bootstrap ----------------------------------------------------

    def sync_from_env(self, keys: list[dict]) -> None:
        """Insert/update keys defined in ENCYCLIST_KEYS env var.

        Each entry is `{"name": "...", "key": "sk-ec-..."}`. We never
        persist the plaintext — only the SHA256 hash. Existing rows for
        the same name are left in place if the hash matches; otherwise
        the row is updated to the new hash.
        """
        for entry in keys:
            name = entry.get("name")
            key = entry.get("key")
            if not name or not key:
                continue
            digest = hash_key(key)
            cur = self._conn.execute(
                "SELECT key_hash FROM ec_api_keys WHERE name = ?", (name,)
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO ec_api_keys(key_hash, name) VALUES (?, ?)",
                    (digest, name),
                )
            elif row[0] != digest:
                self._conn.execute(
                    "DELETE FROM ec_api_keys WHERE name = ?", (name,)
                )
                self._conn.execute(
                    "INSERT INTO ec_api_keys(key_hash, name) VALUES (?, ?)",
                    (digest, name),
                )
        self._conn.commit()

    # ---- runtime ------------------------------------------------------

    def validate(self, plaintext: str) -> Optional[str]:
        if not plaintext:
            return None
        digest = hash_key(plaintext)
        cur = self._conn.execute(
            "SELECT name FROM ec_api_keys WHERE key_hash = ?", (digest,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        self._conn.execute(
            "UPDATE ec_api_keys SET last_used = datetime('now') WHERE key_hash = ?",
            (digest,),
        )
        self._conn.commit()
        return row[0]

    # ---- management ---------------------------------------------------

    def create_key(self, name: str) -> str:
        plaintext = generate_key()
        self._conn.execute(
            "INSERT OR REPLACE INTO ec_api_keys(key_hash, name) VALUES (?, ?)",
            (hash_key(plaintext), name),
        )
        self._conn.commit()
        return plaintext

    def list_keys(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT name, created_at, last_used FROM ec_api_keys ORDER BY name"
        )
        return [
            {"name": r[0], "created_at": r[1], "last_used": r[2]}
            for r in cur.fetchall()
        ]

    def revoke(self, name: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM ec_api_keys WHERE name = ?", (name,)
        )
        self._conn.commit()
        return cur.rowcount > 0

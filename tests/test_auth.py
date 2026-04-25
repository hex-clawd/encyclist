"""API-key auth: env sync, validation, create/list/revoke."""

from __future__ import annotations

from src.auth import hash_key


def test_sync_from_env_inserts_hash_only(auth, conn):
    auth.sync_from_env([{"name": "hermes", "key": "sk-ec-abc"}])
    rows = conn.execute("SELECT name, key_hash FROM ec_api_keys").fetchall()
    assert len(rows) == 1
    assert rows[0]["name"] == "hermes"
    assert rows[0]["key_hash"] == hash_key("sk-ec-abc")
    assert rows[0]["key_hash"] != "sk-ec-abc"  # plaintext never persisted


def test_validate_returns_name(auth):
    auth.sync_from_env([{"name": "hermes", "key": "sk-ec-abc"}])
    assert auth.validate("sk-ec-abc") == "hermes"
    assert auth.validate("sk-ec-wrong") is None
    assert auth.validate("") is None


def test_sync_updates_rotated_keys(auth, conn):
    auth.sync_from_env([{"name": "hermes", "key": "sk-ec-old"}])
    auth.sync_from_env([{"name": "hermes", "key": "sk-ec-new"}])
    assert auth.validate("sk-ec-old") is None
    assert auth.validate("sk-ec-new") == "hermes"


def test_create_and_revoke(auth):
    plaintext = auth.create_key("designer")
    assert plaintext.startswith("sk-ec-")
    assert auth.validate(plaintext) == "designer"

    assert auth.revoke("designer") is True
    assert auth.validate(plaintext) is None

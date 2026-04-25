"""Idempotent first-run init.

The server already runs schema init at import time, so this exists
mainly as a deploy-time hook (`fly ssh console -- python -m src.init`)
so operators can pre-warm the volume and surface key-sync errors before
the first real request lands.
"""

from __future__ import annotations

from src.auth import APIKeyAuth
from src.config import load_config
from src.db import connect, init_schema


def main() -> None:
    config = load_config()
    print(f"[encyclist] data dir: {config.data_dir}")
    print(f"[encyclist] db: {config.db_path}")
    print(f"[encyclist] chroma: {config.chroma_dir}")

    conn = connect(config.db_path)
    init_schema(conn)
    print("[encyclist] schema ready")

    auth = APIKeyAuth(conn)
    auth.sync_from_env(config.keys)
    keys = auth.list_keys()
    print(f"[encyclist] {len(keys)} api key(s) registered: "
          + ", ".join(k["name"] for k in keys))


if __name__ == "__main__":
    main()

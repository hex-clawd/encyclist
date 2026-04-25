"""Test fixtures.

Each test gets an isolated SQLite file. ChromaDB is expensive to spin
up (it loads an ONNX embedding model on first use), so the doc-store
fixture is module-scoped and shared across the doc tests.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is on sys.path so `import src.*` works when
# pytest is invoked from anywhere.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (data / "chroma").mkdir()
    return data


@pytest.fixture
def conn(tmp_data_dir: Path):
    from src.db import connect, init_schema

    db_path = tmp_data_dir / "encyclist.db"
    c = connect(db_path)
    init_schema(c)
    yield c
    c.close()


@pytest.fixture
def entity_store(conn):
    from src.entity_store import EntityStore

    return EntityStore(conn)


@pytest.fixture
def graph(conn):
    from src.graph import Graph

    return Graph(conn)


@pytest.fixture
def auth(conn):
    from src.auth import APIKeyAuth

    return APIKeyAuth(conn)


# ---- Server-level fixtures (env must be set before import) ---------------


@pytest.fixture(scope="session")
def server_env():
    """Configure env vars and return a (data_dir, keys) tuple.

    Server module is import-order sensitive: it loads config at import
    and opens SQLite/Chroma. So this fixture sets env vars in a tmpdir
    once per session, then any test that asks for `app` triggers the
    import lazily.
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="encyclist_test_"))
    keys = [{"name": "test-agent", "key": "sk-ec-test-key-123"}]
    os.environ["ENCYCLIST_DATA_DIR"] = str(tmpdir)
    os.environ["ENCYCLIST_KEYS"] = json.dumps(keys)
    yield tmpdir, keys


@pytest.fixture
def app(server_env):
    """Built ASGI app, rebuilt per test.

    MCP's `StreamableHTTPSessionManager.run()` can only be called once
    per instance. We rebuild the entire MCP app + session manager
    for each test by calling build_app() fresh each time.
    The module-level SQLite/ChromaDB globals are reused since they
    were initialized at first import.
    """
    from src import server

    # Force a new session manager by resetting the internal state
    if hasattr(server.mcp, '_session_manager'):
        server.mcp._session_manager = None
    if hasattr(server.mcp, '_tool_manager'):
        pass  # tool manager is fine to reuse
    return server.build_app()

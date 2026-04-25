"""Runtime configuration for Encyclist."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    data_dir: Path
    db_path: Path
    chroma_dir: Path
    keys_env: str  # raw JSON string from ENCYCLIST_KEYS

    @property
    def keys(self) -> list[dict]:
        if not self.keys_env:
            return []
        try:
            parsed = json.loads(self.keys_env)
        except json.JSONDecodeError as e:
            raise ValueError(f"ENCYCLIST_KEYS is not valid JSON: {e}") from e
        if not isinstance(parsed, list):
            raise ValueError("ENCYCLIST_KEYS must be a JSON array of {name, key}")
        return parsed


def load_config() -> Config:
    data_dir = Path(os.environ.get("ENCYCLIST_DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    chroma_dir = data_dir / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        data_dir=data_dir,
        db_path=data_dir / "encyclist.db",
        chroma_dir=chroma_dir,
        keys_env=os.environ.get("ENCYCLIST_KEYS", ""),
    )

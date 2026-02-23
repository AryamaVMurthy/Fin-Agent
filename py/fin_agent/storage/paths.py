from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path = Path(".finagent")

    @property
    def sqlite_path(self) -> Path:
        return self.root / "state.sqlite"

    @property
    def duckdb_path(self) -> Path:
        return self.root / "analytics.duckdb"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

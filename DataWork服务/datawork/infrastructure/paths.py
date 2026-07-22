"""跨平台应用数据目录。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    database: Path
    files: Path
    reports: Path
    cache: Path

    def ensure(self) -> "WorkspacePaths":
        for directory in (self.root, self.files, self.reports, self.cache):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def default_workspace_root() -> Path:
    override = os.getenv("DATAWORK_HOME")
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system()
    home = Path.home()
    if system == "Windows":
        base = Path(os.getenv("LOCALAPPDATA") or (home / "AppData" / "Local"))
        return base / "DataWork"
    if system == "Darwin":
        return home / "Library" / "Application Support" / "DataWork"
    base = Path(os.getenv("XDG_DATA_HOME") or (home / ".local" / "share"))
    return base / "datawork"


def resolve_workspace_paths(root: str | Path | None = None) -> WorkspacePaths:
    resolved = Path(root).expanduser().resolve() if root else default_workspace_root().resolve()
    return WorkspacePaths(
        root=resolved,
        database=resolved / "workspace.sqlite3",
        files=resolved / "files",
        reports=resolved / "reports",
        cache=resolved / "cache",
    ).ensure()

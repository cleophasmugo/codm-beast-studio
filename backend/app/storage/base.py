"""Storage interface.

The app only touches files through this interface, so an S3-compatible backend can be
added by implementing the same methods (put a local file, open/stream by key, delete,
and give a local path for FFmpeg, downloading to a cache first when the backend is remote).
Only LocalStorage ships today.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Protocol

from ..core.config import get_settings
from ..core.security import safe_join


class Storage(Protocol):
    def new_key(self, prefix: str, ext: str) -> str: ...
    def path_for(self, key: str) -> Path: ...
    def put_file(self, src: Path, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def size(self, key: str) -> int: ...
    def delete(self, key: str | None) -> None: ...
    def usage_bytes(self) -> dict[str, int]: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def new_key(self, prefix: str, ext: str) -> str:
        ext = "".join(c for c in ext.lower() if c.isalnum())[:8]
        return f"{prefix}/{uuid.uuid4().hex}{'.' + ext if ext else ''}"

    def path_for(self, key: str) -> Path:
        p = safe_join(self.root, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_file(self, src: Path, key: str) -> None:
        dst = self.path_for(key)
        if Path(src).resolve() != dst:
            shutil.move(str(src), dst)

    def exists(self, key: str) -> bool:
        try:
            return safe_join(self.root, key).is_file()
        except ValueError:
            return False

    def size(self, key: str) -> int:
        return safe_join(self.root, key).stat().st_size

    def delete(self, key: str | None) -> None:
        if not key:
            return
        try:
            safe_join(self.root, key).unlink(missing_ok=True)
        except ValueError:
            pass

    def usage_bytes(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for sub in self.root.iterdir() if self.root.exists() else []:
            if sub.is_dir():
                out[sub.name] = sum(f.stat().st_size for f in sub.rglob("*") if f.is_file())
        return out


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    root = get_settings().dir("files")
    if _storage is None or _storage.root != root.resolve():
        _storage = LocalStorage(root)
    return _storage

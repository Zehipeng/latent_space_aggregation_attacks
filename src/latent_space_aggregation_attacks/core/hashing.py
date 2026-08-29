from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def sha256_tree(path: str | Path) -> tuple[str, int, int]:
    """Hash relative paths, file sizes, and file hashes in deterministic order."""
    root = Path(path).resolve()
    if root.is_file():
        return sha256_file(root), root.stat().st_size, 1
    if not root.is_dir():
        raise FileNotFoundError(root)
    digest = hashlib.sha256(); total_size = 0; count = 0
    for file_path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        relative = file_path.relative_to(root).as_posix(); size = file_path.stat().st_size; file_hash = sha256_file(file_path)
        digest.update(f"{relative}\0{size}\0{file_hash}\n".encode("utf-8")); total_size += size; count += 1
    return digest.hexdigest(), total_size, count

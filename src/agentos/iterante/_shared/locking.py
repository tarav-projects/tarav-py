"""File.Locking — a persisted per-file version registry.

A permission system that tracks the authorized version of each file in a declared
set. A legal write goes through `record()`, which appends the file's content hash
as its new authorized version to a per-file append-only `.jsonl` log. `verify()`
holds: a file is valid iff its current content hash matches the latest logged
version — a mismatch (or no log) means it was edited outside the system.

This implementation is shared by both maintained Iterante runtimes.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

WRITER = "system"
LOG_SUFFIX = ".lock.jsonl"


class LockViolation(Exception):
    """A tracked file changed outside the system's editor."""


def _log_path(path: Path) -> Path:
    return path.parent / (path.name + LOG_SUFFIX)


def _content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _latest_version(log: Path) -> str | None:
    if not log.is_file():
        return None
    version = None
    for line in log.read_text().splitlines():
        if line.strip():
            version = json.loads(line)["version"]
    return version


def record(path: Path) -> None:
    """Sign the file's current content as its new authorized version."""
    event = {"version": _content_hash(path), "writer": WRITER}
    with _log_path(path).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def verify(path: Path) -> None:
    """Raise LockViolation if the file differs from its latest authorized version."""
    expected = _latest_version(_log_path(path))
    if expected is None:
        raise LockViolation(f"{path} has no authorized version on record")
    if _content_hash(path) != expected:
        raise LockViolation(f"{path} changed outside the system")

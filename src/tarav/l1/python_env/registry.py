"""Best-effort registry of the Python code that `tarav run` executes.

Agents read it to see how Tarav was recently used, here and in other Projects.
Nothing depends on it: every failure is logged and the run proceeds unchanged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ENTRY_LIMIT_BYTES = 1_000_000
PARTITION_LIMIT_BYTES = 50_000_000
GLOBAL_PARTITION = "global"
ENTRY_FILENAME = "entry.json"
SOURCE_FILENAME = "source.py"
_LOG = logging.getLogger(__name__)


def registry_root() -> Path:
    """The machine-local registry folder; one subfolder per partition.

    ``TARAV_RUN_REGISTRY`` relocates it, which test suites use so that the
    code they run does not land among real examples. Otherwise the Tarav home.
    """
    override = os.getenv("TARAV_RUN_REGISTRY")
    if override:
        return Path(override).expanduser().resolve()
    home = os.getenv("TARAV_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".tarav"
    return base.resolve() / "run-registry"


@dataclass(frozen=True)
class RunEntry:
    """One retained run: its folder and the metadata written so far."""

    directory: Path
    record: dict[str, object]

    @property
    def id(self) -> str:
        return self.directory.name


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_record(entry: RunEntry) -> None:
    target = entry.directory / ENTRY_FILENAME
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(entry.record, indent=2, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.replace(temporary, target)


def _size(directory: Path) -> int:
    return sum(path.stat().st_size for path in directory.iterdir() if path.is_file())


# tarav.breadcrumb 93544869b38e
class RunRegistry:
    """Retain what ran, partitioned by Project, bounded by size."""

    # tarav.breadcrumb 5dde5c0363aa
    def __init__(
        self, root: Path | None = None, *,
        entry_limit: int = ENTRY_LIMIT_BYTES,
        partition_limit: int = PARTITION_LIMIT_BYTES,
    ) -> None:
        self.root = Path(root) if root is not None else registry_root()
        self.entry_limit = entry_limit
        self.partition_limit = partition_limit

    def begin(
        self, *, partition: str | None, source: bytes | None,
        metadata: Mapping[str, object],
    ) -> RunEntry | None:
        """Record a run before it starts, so a crash or hang is still retained."""
        try:
            folder = self.root / (partition or GLOBAL_PARTITION)
            folder.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            record: dict[str, object] = {**metadata, "started_at": _now(), "exit_code": None}
            digest = "nosource"
            if source is not None:
                digest = hashlib.sha256(source).hexdigest()
                record.update(content_hash=digest, size=len(source),
                              truncated=len(source) > self.entry_limit)
            previous = self._newest(folder)
            entry = RunEntry(folder / f"{stamp}-{digest[:12]}", record)
            entry.directory.mkdir()
            if source is not None:
                self._retain_source(entry, source, previous, digest)
            _write_record(entry)
            self._prune(folder, keep=entry.directory)
            return entry
        except Exception:
            _LOG.warning("Could not retain run registry entry", exc_info=True)
            return None

    def finish(self, entry: RunEntry | None, *, exit_code: int | None) -> None:
        """Complete an entry with the outcome of its run."""
        if entry is None:
            return
        try:
            if not entry.directory.is_dir():
                return
            entry.record.update(exit_code=exit_code, finished_at=_now())
            _write_record(entry)
        except Exception:
            _LOG.warning("Could not complete run registry entry", exc_info=True)

    def _newest(self, folder: Path) -> Path | None:
        entries = sorted(path for path in folder.iterdir() if path.is_dir())
        return entries[-1] if entries else None

    def _retain_source(
        self, entry: RunEntry, source: bytes, previous: Path | None, digest: str,
    ) -> None:
        target = entry.directory / SOURCE_FILENAME
        # The same code run twice in a row shares one file; a hard link keeps
        # each entry complete when the older one is pruned.
        if previous is not None and previous.name.endswith("-" + digest[:12]):
            try:
                os.link(previous / SOURCE_FILENAME, target)
                return
            except OSError:
                pass
        target.write_bytes(source[: self.entry_limit])

    def _prune(self, folder: Path, *, keep: Path) -> None:
        entries = sorted(path for path in folder.iterdir() if path.is_dir())
        total = sum(_size(path) for path in entries)
        for path in entries:
            if total <= self.partition_limit:
                return
            if path == keep:
                continue
            total -= _size(path)
            shutil.rmtree(path, ignore_errors=True)


__all__ = [
    "ENTRY_LIMIT_BYTES",
    "GLOBAL_PARTITION",
    "PARTITION_LIMIT_BYTES",
    "RunEntry",
    "RunRegistry",
    "registry_root",
]

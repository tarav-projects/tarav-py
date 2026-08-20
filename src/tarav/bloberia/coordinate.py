# $kw: --from Agentos.Bloberia --note [DF] a Record.Coordinate is commit + file + path-in-file, derived on request and never allocated
"""The stable reference: `commit + file + path-in-file`.

A coordinate is **derived, not allocated**. It is already fully determined by where the
record sits, so bloberia mints nothing, stores no mapping, and adds no field to cargo. The
alternative considered — a store-minted opaque handle returned by `insert` — would have
made the store own an identity, and therefore a schema.

It is read-side. You obtain one by asking about a record you already have, so writing is
unchanged and arity stays at the call site.

**An uncommitted record has no coordinate.** Not a placeholder, not a HEAD-relative form,
and emphatically not a commit fired to manufacture one: the coordinate is a fact about git
history, and if the record is not in history there is no fact to report. A record whose
file is modified since HEAD counts as uncommitted for the same reason — the committed
bytes are a different record than the one in hand.

What makes this work is that git preserves each commit's tree as it was. A coordinate keeps
resolving across a later change of storage topology, because it names the old commit, where
the old layout is still what the tree holds. The private layout and the permanent reference
turn out to be compatible rather than opposed.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

_MISSING = object()


class CoordinateError(RuntimeError):
    pass


@dataclass(frozen=True)
class RecordCoordinate:
    """One immutable position: a commit, a file in it, and a path inside that file."""

    commit: str
    file: str
    path: str = ""

    def __str__(self) -> str:
        suffix = f"#{self.path}" if self.path else ""
        return f"bloberia:{self.commit}/{self.file}{suffix}"

    @classmethod
    def parse(cls, text: str) -> "RecordCoordinate":
        if not text.startswith("bloberia:"):
            raise CoordinateError(f"not a bloberia coordinate: {text!r}")
        body, _, path = text[len("bloberia:") :].partition("#")
        commit, _, file = body.partition("/")
        if not commit or not file:
            raise CoordinateError(f"incomplete coordinate: {text!r}")
        return cls(commit=commit, file=file, path=path)


def derive(repo: Path, file: Path, path: str = "") -> RecordCoordinate | None:
    """The coordinate of `file` as git currently holds it, or None if git does not."""
    try:
        relative = file.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return None
    if _git(repo, "status", "--porcelain", "--", relative).stdout.strip():
        return None
    commit = _git(repo, "log", "-1", "--format=%H", "--", relative).stdout.strip()
    if not commit:
        return None
    return RecordCoordinate(commit=commit, file=relative, path=path)


def resolve(repo: Path, coordinate: RecordCoordinate) -> object:
    """Read the value a coordinate names, out of the commit it names."""
    result = _git(repo, "show", f"{coordinate.commit}:{coordinate.file}")
    if result.returncode:
        raise CoordinateError(
            f"cannot read {coordinate.file} at {coordinate.commit}: {result.stderr.strip()}"
        )
    try:
        value: object = json.loads(result.stdout)
    except ValueError as exc:
        raise CoordinateError(f"{coordinate.file} at {coordinate.commit} is not JSON") from exc
    for segment in filter(None, coordinate.path.split(".")):
        value = _step(value, segment)
        if value is _MISSING:
            raise CoordinateError(f"no such path in {coordinate}: {coordinate.path!r}")
    return value


def _step(value: object, segment: str) -> object:
    if isinstance(value, dict):
        return value.get(segment, _MISSING)
    if isinstance(value, list) and segment.lstrip("-").isdigit():
        index = int(segment)
        return value[index] if -len(value) <= index < len(value) else _MISSING
    return _MISSING


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(repo), *args), capture_output=True, text=True, check=False
    )


__all__ = ["CoordinateError", "RecordCoordinate", "derive", "resolve"]

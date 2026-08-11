# $kw: --from File.Numbering.Protocol
from __future__ import annotations

from pathlib import Path


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return tuple(unique)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)

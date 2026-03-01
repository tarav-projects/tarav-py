from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
)


@dataclass(frozen=True)
class PrefixScanConfig:
    root: Path
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    width: int


def _normalize_rel(rel: PurePosixPath) -> str:
    value = rel.as_posix()
    return "" if value == "." else value


def _should_exclude(rel_path: PurePosixPath, patterns: tuple[str, ...]) -> bool:
    rel_value = _normalize_rel(rel_path)
    rel_parts = set(rel_path.parts)

    for raw_pattern in patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue

        if rel_value == pattern or rel_value.startswith(f"{pattern}/"):
            return True

        # A bare directory name excludes that folder anywhere in the tree.
        if "/" not in pattern and pattern in rel_parts:
            return True

        if rel_value and PurePosixPath(rel_value).match(pattern):
            return True
    return False


def _candidate_roots(config: PrefixScanConfig) -> list[Path]:
    if not config.includes:
        return [config.root]

    candidates: list[Path] = []
    for include in config.includes:
        target = (config.root / include).resolve()
        if target.exists():
            candidates.append(target)
    return candidates


def collect_prefixes(config: PrefixScanConfig) -> set[int]:
    pattern = re.compile(rf"^(\d{{{config.width}}})-")
    prefixes: set[int] = set()

    for candidate in _candidate_roots(config):
        if candidate.is_file():
            match = pattern.match(candidate.name)
            if match:
                prefixes.add(int(match.group(1)))
            continue

        for dirpath, dirnames, filenames in os.walk(candidate):
            current = Path(dirpath)
            rel_current = PurePosixPath(
                _normalize_rel(PurePosixPath(current.relative_to(config.root).as_posix()))
            )
            if _should_exclude(rel_current, config.excludes):
                dirnames[:] = []
                continue

            pruned: list[str] = []
            for dirname in dirnames:
                rel_dir = PurePosixPath(
                    _normalize_rel(
                        PurePosixPath((current / dirname).relative_to(config.root).as_posix())
                    )
                )
                if not _should_exclude(rel_dir, config.excludes):
                    pruned.append(dirname)
            dirnames[:] = pruned

            for filename in filenames:
                match = pattern.match(filename)
                if match:
                    prefixes.add(int(match.group(1)))
    return prefixes


def next_prefix_value(prefixes: set[int], minimum: int) -> int:
    eligible = [value for value in prefixes if value >= minimum]
    if not eligible:
        return minimum
    return max(eligible) + 1


def format_prefix(value: int, width: int) -> str:
    return f"{value:0{width}d}"


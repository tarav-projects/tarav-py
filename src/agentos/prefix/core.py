from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from agentos._core.scan import DEFAULT_SCAN_EXCLUDES, iter_target_files


DEFAULT_EXCLUDES = DEFAULT_SCAN_EXCLUDES


@dataclass(frozen=True)
class PrefixScanConfig:
    root: Path
    includes: tuple[str, ...]
    excludes: tuple[str, ...]
    width: int


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
        for file_path in iter_target_files(
            root=config.root,
            target=candidate,
            excludes=config.excludes,
            recursive=True,
        ):
            match = pattern.match(file_path.name)
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

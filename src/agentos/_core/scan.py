# $kw: --from Project.Discovery.System
from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence


DEFAULT_SCAN_EXCLUDES = (
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
)


def normalize_rel(rel: PurePosixPath) -> str:
    value = rel.as_posix()
    return "" if value == "." else value


def should_exclude(rel_path: PurePosixPath, patterns: tuple[str, ...]) -> bool:
    rel_value = normalize_rel(rel_path)
    rel_parts = set(rel_path.parts)

    for raw_pattern in patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue

        if rel_value == pattern or rel_value.startswith(f"{pattern}/"):
            return True


        if "/" not in pattern and pattern in rel_parts:
            return True

        if rel_value and PurePosixPath(rel_value).match(pattern):
            return True
    return False


def iter_target_files(
    *,
    root: Path,
    target: Path,
    excludes: tuple[str, ...],
    recursive: bool,
) -> Iterator[Path]:
    if target.is_file():
        rel_target = PurePosixPath(target.relative_to(root).as_posix())
        if not should_exclude(rel_target, excludes):
            yield target
        return

    if not target.is_dir():
        return

    if recursive:
        for dirpath, dirnames, filenames in os.walk(target):
            current = Path(dirpath)
            rel_current = PurePosixPath(
                normalize_rel(PurePosixPath(current.relative_to(root).as_posix()))
            )
            if should_exclude(rel_current, excludes):
                dirnames[:] = []
                continue

            pruned: list[str] = []
            for dirname in dirnames:
                rel_dir = PurePosixPath(
                    normalize_rel(
                        PurePosixPath((current / dirname).relative_to(root).as_posix())
                    )
                )
                if not should_exclude(rel_dir, excludes):
                    pruned.append(dirname)
            dirnames[:] = pruned

            for filename in filenames:
                file_path = current / filename
                rel_file = PurePosixPath(file_path.relative_to(root).as_posix())
                if not should_exclude(rel_file, excludes):
                    yield file_path
        return

    for child in target.iterdir():
        if not child.is_file():
            continue
        rel_file = PurePosixPath(child.relative_to(root).as_posix())
        if not should_exclude(rel_file, excludes):
            yield child


def resolve_root_dir(raw_root: Path) -> Path:
    root = raw_root.expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"error: root path does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"error: root path is not a directory: {root}")
    return root


def resolve_targets_under_root(root: Path, raw_targets: Sequence[str]) -> tuple[Path, ...]:
    targets = tuple(raw_targets) if raw_targets else (".",)
    resolved_targets: list[Path] = []

    for raw_target in targets:
        candidate = Path(raw_target).expanduser()
        resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
        if not resolved.exists():
            raise SystemExit(f"error: target path does not exist: {raw_target}")
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"error: target path escapes --root: {raw_target}") from exc
        resolved_targets.append(resolved)

    return tuple(resolved_targets)


def resolve_relative_paths_under_root(
    root: Path,
    raw_paths: Sequence[str],
    *,
    option_name: str,
) -> tuple[str, ...]:
    normalized_paths: list[str] = []
    for raw_path in raw_paths:
        candidate = Path(raw_path)
        if candidate.is_absolute():
            raise SystemExit(f"error: --{option_name} paths must be relative to --root")

        resolved = (root / candidate).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SystemExit(f"error: {option_name} path escapes --root: {raw_path}") from exc
        normalized_paths.append(str(candidate))

    return tuple(normalized_paths)

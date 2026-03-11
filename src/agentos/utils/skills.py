from __future__ import annotations

import os
from pathlib import Path

from agentos._core.errors import CliError

SKILL_MARKER_FILENAME = "SKILL.md"


def resolve_project_root() -> Path:
    env_root = os.getenv("AGENTOS_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def skills_dir() -> Path:
    return resolve_project_root() / "skills"


def list_skill_names() -> list[str]:
    root = skills_dir()
    if not root.exists():
        return []

    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return sorted(names)


def discover_nested_skill_dirs(root: Path) -> list[Path]:
    normalized_root = root.expanduser().resolve()
    nested: list[Path] = []

    def walk(current_path: Path, ancestor_dirs: set[Path]) -> None:
        try:
            entries = sorted(current_path.iterdir(), key=lambda entry: entry.name)
        except OSError:
            return

        filenames = {entry.name for entry in entries if entry.is_file()}
        if current_path != normalized_root:
            relative_path = current_path.relative_to(normalized_root)
            if len(relative_path.parts) > 1 and SKILL_MARKER_FILENAME in filenames:
                nested.append(current_path)
                return

        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue

            resolved_entry = entry.resolve()
            if resolved_entry in ancestor_dirs:
                continue
            walk(entry, ancestor_dirs | {resolved_entry})

    walk(normalized_root, {normalized_root})

    nested.sort(key=lambda path: path.relative_to(normalized_root).as_posix())
    return nested


def _resolved_symlink_target(path: Path) -> Path:
    link_target = Path(os.readlink(path))
    if link_target.is_absolute():
        return link_target.resolve()
    return (path.parent / link_target).resolve()


def discover_broken_symlinks(root: Path) -> list[Path]:
    normalized_root = root.expanduser().resolve()
    broken: list[Path] = []

    def walk(current_path: Path) -> None:
        try:
            entries = sorted(current_path.iterdir(), key=lambda entry: entry.name)
        except OSError:
            return

        for entry in entries:
            if entry.is_symlink():
                if not entry.exists():
                    broken.append(entry)
                continue

            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue

            walk(entry)

    walk(normalized_root)

    broken.sort(key=lambda path: path.relative_to(normalized_root).as_posix())
    return broken


def flatten_skills_root(
    root: Path,
    *,
    dry_run: bool = False,
    overwrite: bool = False,
) -> tuple[list[Path], list[Path], list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    normalized_root = root.expanduser().resolve()
    if not normalized_root.exists():
        raise CliError(f"skills root does not exist: {normalized_root}")
    if not normalized_root.is_dir():
        raise CliError(f"skills root is not a directory: {normalized_root}")

    nested_skill_dirs = discover_nested_skill_dirs(normalized_root)

    skill_name_to_paths: dict[str, list[Path]] = {}
    for skill_dir in nested_skill_dirs:
        skill_name_to_paths.setdefault(skill_dir.name, []).append(skill_dir)

    duplicate_names = {
        name: paths for name, paths in skill_name_to_paths.items() if len(paths) > 1
    }
    if duplicate_names:
        duplicate_entries = ", ".join(
            f"{name} ({', '.join(str(path.relative_to(normalized_root)) for path in paths)})"
            for name, paths in sorted(duplicate_names.items())
        )
        raise CliError(
            f"duplicate nested skill names under {normalized_root}: {duplicate_entries}"
        )

    create_specs: list[tuple[Path, Path]] = []
    overwrite_specs: list[tuple[Path, Path]] = []
    matching_skips: list[tuple[Path, Path]] = []
    conflict_skips: list[tuple[Path, Path]] = []
    for skill_dir in nested_skill_dirs:
        link_path = normalized_root / skill_dir.name
        relative_target = skill_dir.relative_to(normalized_root)

        if link_path.exists() or link_path.is_symlink():
            if link_path.is_symlink() and _resolved_symlink_target(link_path) == skill_dir.resolve():
                matching_skips.append((link_path, skill_dir))
                continue
            if overwrite and link_path.is_symlink():
                overwrite_specs.append((link_path, relative_target))
                continue
            conflict_skips.append((link_path, skill_dir))
            continue

        create_specs.append((link_path, relative_target))

    if not dry_run:
        for link_path, _ in overwrite_specs:
            link_path.unlink()
        for link_path, relative_target in create_specs + overwrite_specs:
            link_path.symlink_to(relative_target, target_is_directory=True)

    created_links = [link_path for link_path, _ in create_specs]
    overwritten_links = [link_path for link_path, _ in overwrite_specs]
    return created_links, overwritten_links, matching_skips, conflict_skips


def prune_broken_skill_symlinks(
    root: Path,
    *,
    dry_run: bool = False,
) -> list[Path]:
    normalized_root = root.expanduser().resolve()
    if not normalized_root.exists():
        raise CliError(f"skills root does not exist: {normalized_root}")
    if not normalized_root.is_dir():
        raise CliError(f"skills root is not a directory: {normalized_root}")

    broken_symlinks = discover_broken_symlinks(normalized_root)
    if not dry_run:
        for path in broken_symlinks:
            path.unlink()

    return broken_symlinks

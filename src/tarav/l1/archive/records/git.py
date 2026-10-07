"""Git placement policy within Archive's Record-storage partitions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tarav.l0._core.git_repository import initialize_repository as _initialize_repository
# tarav.breadcrumb be55aa1795b6cd35b1a97c77d00706182d212063250726b8198935df93fe53cd


GIT_CONFIG_FILENAME = "git-config.json"
GitMode = Literal["auto", "new", "inherit"]


@dataclass(frozen=True)
class GitPlacement:
    mode: GitMode
    source: Path | None
    parent_repository: Path | None

    @property
    def initialize(self) -> bool:
        if self.mode == "new":
            return True
        if self.mode == "inherit":
            if self.parent_repository is None:
                raise ValueError("Git policy requires a parent repository")
            return False
        return self.parent_repository is None


def _git_marker(directory: Path) -> bool:
    marker = directory / ".git"
    return marker.is_dir() or marker.is_file()


def _parents_through(directory: Path, boundary: Path):
    directory = directory.resolve()
    boundary = boundary.resolve()
    if not directory.is_relative_to(boundary):
        raise ValueError("Archive Git lookup escapes its Workflow partition")
    while True:
        yield directory
        if directory == boundary:
            return
        directory = directory.parent


def repository_root(directory: Path, workflow_root: Path) -> Path | None:
    """Find only a repository below the Workflow partition, never above it."""

    if _git_marker(workflow_root):
        raise ValueError("Workflow partition must not be a Git repository")
    for parent in _parents_through(directory, workflow_root):
        if parent == workflow_root:
            return None
        if _git_marker(parent):
            return parent
    return None


def _read_mode(path: Path) -> GitMode:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"children"}:
        raise ValueError(f"Archive Git config must contain only 'children': {path}")
    mode = value["children"]
    if mode not in ("auto", "new", "inherit"):
        raise ValueError(f"Invalid Archive Git children policy in {path}: {mode!r}")
    return mode


def placement_for_child(parent: Path, workflow_root: Path) -> GitPlacement:
    """Resolve a directory's child policy, stopping at its nearest repository."""

    repository = repository_root(parent, workflow_root)
    for directory in _parents_through(parent, workflow_root):
        config = directory / GIT_CONFIG_FILENAME
        if config.exists():
            return GitPlacement(_read_mode(config), config, repository)
        if directory == repository:
            break
    return GitPlacement("auto", None, repository)


def placement_for_nested_child(parent: Path, archive_root: Path) -> GitPlacement:
    """Resolve an Archive artifact's child policy within its parent Archive."""

    # An Archive may inherit a repository created at an enclosing run, or own
    # one itself. Its local configuration does not look above this Archive.
    repository = None
    current = parent.resolve()
    while True:
        if _git_marker(current):
            repository = current
            break
        if current == current.parent:
            break
        current = current.parent
    for directory in _parents_through(parent, archive_root):
        config = directory / GIT_CONFIG_FILENAME
        if config.exists():
            return GitPlacement(_read_mode(config), config, repository)
        if directory == repository:
            break
    return GitPlacement("auto", None, repository)


def initialize_repository(directory: Path) -> None:
    _initialize_repository(directory)

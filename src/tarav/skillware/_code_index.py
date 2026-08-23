# $kw: ^skw-code-index --from Index.Primary.Surface --from Skw.Network --note [DF] Index adapter for language-neutral code dependency checks ^c20260811-73u
"""Resolve code annotation dependencies against the Index records."""

from __future__ import annotations

from pathlib import Path

from tarav.indexlab import IndexResolutionError
from tarav.skillware.index_surfaces import IndexSurfaceProvider

from ._code_model import CodeDependencyResolver


class EmptyCodeDependencyResolver:
    def resolve(self, names: set[str]) -> dict[str, str]:
        return {name: "unresolved:no Index records reachable" for name in names}

    def collisions(self, names: set[str]) -> dict[str, list[str]]:
        return {}


def index_code_dependency_resolver(start: Path | str) -> CodeDependencyResolver:
    """The record-backed resolver for the project enclosing `start`."""
    try:
        return IndexSurfaceProvider.for_path(start)
    except IndexResolutionError:
        return EmptyCodeDependencyResolver()

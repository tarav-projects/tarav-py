# $kw: ^skw-code-index --from Index.Depot --from Skw.Network --note [DF] Index adapter for language-neutral code dependency checks ^c20260811-73u
"""Resolve code annotation dependencies against engaged Index depots."""

from __future__ import annotations

from pathlib import Path

from tarav.index.drift import IndexSurfaceProvider

from ._code_model import CodeDependencyResolver


class EmptyCodeDependencyResolver:
    def resolve(self, names: set[str]) -> dict[str, str]:
        return {name: "unresolved:no Index depots configured" for name in names}

    def collisions(self, names: set[str]) -> dict[str, list[Path]]:
        return {}


def index_code_dependency_resolver(
    depots: tuple[Path, ...],
) -> CodeDependencyResolver:
    if not depots:
        return EmptyCodeDependencyResolver()
    return IndexSurfaceProvider(
        depots[0],
        engaged_depots=depots[1:],
    )

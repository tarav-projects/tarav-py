"""Default dependency resolution for Skillware code surfaces.

Consumers may inject a richer resolver. The core Skillware implementation does
not silently bind semantic names to an unrelated annotation system.
"""

from __future__ import annotations

from pathlib import Path

from ._code_model import CodeDependencyResolver


class UnresolvedCodeDependencyResolver:
    def resolve(self, names: set[str]) -> dict[str, str]:
        return {name: "unresolved:no dependency resolver configured" for name in names}

    def collisions(self, names: set[str]) -> dict[str, list[str]]:
        return {}


def code_dependency_resolver(_start: Path | str) -> CodeDependencyResolver:
    """Return the neutral default used when no consumer resolver is injected."""

    return UnresolvedCodeDependencyResolver()


__all__ = ["UnresolvedCodeDependencyResolver", "code_dependency_resolver"]

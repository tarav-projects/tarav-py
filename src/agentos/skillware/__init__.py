"""Skillware: the skill-development compilation system.

`.skillware/src/**/*.skw.md` sources compile to a skill's runnable files;
`agentos skillware build/check/status` is the deterministic toolchain.
"""

from agentos.skillware.model import SkwFinding, SkwRecipe, SkwSource, parse_skw_source

__all__ = [
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
]

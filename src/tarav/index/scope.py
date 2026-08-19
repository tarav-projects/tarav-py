# $kw: --from Line.Scope --note [DF] a line's scope is one Skw.Address.Schema address, not a depot/chapter/concept triple
"""`Line.Scope` — where a line is grouped.

A line is grouped under a scope, and a scope may be a `Kernel.Block` **or another annotation
attachment point**. Both are addresses in one grammar (`Skw.Address.Schema`), and the schema
is explicit that *name syntax does not change the named entity's semantics* — so one field,
one resolver, two address kinds.

```text
tarav-pkg/design#Scope.Axis        Block.Path     → a Kernel.Block in a chapter
@src/tarav/index/linter.py/Finding       Locator.Name   → a Skw.Annotation attachment point
```

This is what makes "index lines attach to any skw annotation through the same mechanism as
the markdown index" true in the implementation rather than only in the design.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .config import TaravIndexError

#: `<depot>/<chapter>#<Concept.Name>`
BLOCK_PATH_RE = re.compile(
    r"^(?P<depot>[A-Za-z0-9._-]+)/(?P<chapter>[A-Za-z0-9._-]+)#(?P<concept>[A-Za-z0-9._-]+)$"
)
#: `@<file path>/<region>` — the `@` is agent-maintained and may be omitted on input.
LOCATOR_RE = re.compile(r"^@?(?P<path>[^\s@]+?\.[A-Za-z0-9]+)(?:/(?P<region>[^\s]+))?$")


class ScopeError(TaravIndexError):
    """Raised when a scope address cannot be parsed or resolved."""


class ScopeKind(StrEnum):
    #: A concept block in an index chapter.
    BLOCK = "block"
    #: An annotation attachment point on an ordinary product surface.
    ANNOTATION = "annotation"


@dataclass(frozen=True, slots=True)
class LineScope:
    """One address in `Skw.Address.Schema`, plus the parts a resolver needs."""

    kind: ScopeKind
    address: str
    #: Block.Path parts
    depot: str | None = None
    chapter: str | None = None
    concept: str | None = None
    #: Locator.Name parts
    file: str | None = None
    region: str | None = None

    @property
    def label(self) -> str:
        """The human-facing grouping name, whichever kind this is."""

        return self.concept or self.region or (self.file or self.address)

    def __str__(self) -> str:
        return self.address


def parse_scope(address: str) -> LineScope:
    """Parse a scope address.

    `Block.Path` is tried first: it is the more constrained form, and a bare
    `a/b#c` is never a legal locator.
    """

    address = address.strip()
    if not address:
        raise ScopeError("scope address is empty")

    block = BLOCK_PATH_RE.match(address)
    if block is not None:
        return LineScope(
            kind=ScopeKind.BLOCK,
            address=address,
            depot=block.group("depot"),
            chapter=block.group("chapter"),
            concept=block.group("concept"),
        )

    locator = LOCATOR_RE.match(address)
    if locator is not None:
        path = locator.group("path")
        region = locator.group("region")
        return LineScope(
            kind=ScopeKind.ANNOTATION,
            # The `@` is agent-maintained: canonicalize it on the way in.
            address=f"@{path}" + (f"/{region}" if region else ""),
            file=path,
            region=region,
        )

    raise ScopeError(
        f"not a legal scope address: {address!r} "
        "(expected `<depot>/<chapter>#<Concept>` or `@<file>/<region>`)"
    )


def block_scope(depot: str, chapter: str, concept: str) -> LineScope:
    return parse_scope(f"{depot}/{chapter}#{concept}")


def annotation_scope(file: str, region: str | None = None) -> LineScope:
    return parse_scope(f"@{file}" + (f"/{region}" if region else ""))


def resolve_scope_surface(
    scope: LineScope, root: Path, *, contains: str | None = None
) -> Path | None:
    """The surface file a scope lives on, or ``None`` when it cannot be located.

    A block resolves through the depot's home layout; an annotation resolves directly to its
    product file. Both answer the same question, which is the point of one address space.

    A `Block.Path` names a depot and a chapter, never a home — homes are a geography of the
    same depot, and no home is the SSOT. So every home is searched, and a chapter that exists
    in one of them resolves.

    ``contains`` disambiguates when several files answer to the same chapter — `100-design.md`
    and `900-design.md` both are the ``design`` chapter. Pass the label of a line known to be
    on the surface and the file holding it wins; without it the first match is returned, which
    is right only when there is one.
    """

    if scope.kind is ScopeKind.ANNOTATION:
        return root / scope.file if scope.file else None

    if not (scope.depot and scope.chapter):
        return None

    homes = root / "skills" / scope.depot / "homes"
    matches = sorted(homes.glob(f"*/chapters/*-{scope.chapter}.md"))
    if not matches:
        return None
    if contains:
        for candidate in matches:
            try:
                if contains in candidate.read_text("utf-8"):
                    return candidate
            except OSError:
                continue
    return matches[0]


__all__ = [
    "BLOCK_PATH_RE",
    "LOCATOR_RE",
    "LineScope",
    "ScopeError",
    "ScopeKind",
    "annotation_scope",
    "block_scope",
    "parse_scope",
    "resolve_scope_surface",
]

# $kw: ^index-skw-network --from POI.System --from POI.Linter --from Index.Primary.Surface --note [CT] Index drift consumes domain-owned Skw.Network findings before POI adaptation ^c20260729-49u --note [DC] resolution is global within one Index.Workspace, so depot visibility stops being a resolution rule and a name defined twice becomes an ordinary reportable collision instead of a lookup order
"""The index `Skw.Backend`'s binding into the shared linter core.

Implements `SurfaceProvider` (`tarav.skw.network`) over the Index records so the
surface-agnostic drift engine can run over the Index — the extensibility point of
Impl.Req 700: a new surface is a new provider, no new engine.

The Index declares no block->block edges (blocks reference each other only via
`Dotted.Name` mentions), so `declared_edges` is empty and the meaningful check is
`dangling_mention_findings`: a mention that no longer resolves.

The resolver still over-reports on the real corpus. It models block headings,
`Inline.Definition`s and declared aliases, but not canonical/plural short-forms
(`Stable.Surfaces` -> `Stable.Surface`), `::`-scoped names, or illustrative example
placeholders. That is documented follow-up resolver work, not a defect in this binding.
"""

from __future__ import annotations

from pathlib import Path

from tarav.indexlab import IndexResolver, line_type
from tarav.indexlab.projection import ProjectedLine
from tarav.skw.network import (
    NetworkFinding,
    dangling_mention_findings,
    extract_mentions,
    network_finding,
)

#: Chapters whose `[DF]` lines may carry an `Inline.Definition`.
DEFINING_CHAPTERS = ("design", "index")


def concept_of(block_name: str) -> str:
    """The concept a block address names, without its depot or surface prefix."""
    _, _, concept = block_name.partition("#")
    return concept


def chapter_of(block_name: str) -> str:
    """The chapter a block lives in, or `""` for a block written on a product surface."""
    scope, _, _ = block_name.partition("#")
    if scope.startswith("@"):
        return ""
    _, _, chapter = scope.rpartition("/")
    return chapter


def _first_cited_concept(line: ProjectedLine) -> str | None:
    for mention in sorted(extract_mentions(line.text)):
        return mention
    return None


class IndexSurfaceProvider:
    """`SurfaceProvider` over the Index records of one `Index.Workspace`.

    Mentions come from the record line text; resolution runs against every concept
    the corpus *defines* — block headings, `Inline.Definition`s, and declared aliases.
    """

    def __init__(self, resolver: IndexResolver) -> None:
        self._resolver = resolver
        self.unresolved_dependencies: list[str] = []
        self._concepts: dict[str, str] = {}
        self._defining: dict[str, list[str]] = {}
        self._index()

    @classmethod
    def for_path(cls, start: Path | str) -> IndexSurfaceProvider:
        return cls(IndexResolver.for_path(start))

    # $kw: --note [DC] a block's own first [DF] restates the heading, so only *other* [DF] subjects count as an Inline.Definition; taking every [DF] subject would make each block define itself twice
    def _index(self) -> None:
        for block in self._resolver.blocks():
            concept = concept_of(block.name)
            if concept:
                self._define(concept, block.name, block.name)
            defining_chapter = chapter_of(block.name) in DEFINING_CHAPTERS
            for alias in self._resolver.aliases(block.name):
                self._define(alias, block.name, alias)
            if not defining_chapter:
                continue
            for line in self._resolver.lines(block.name):
                if line_type(line) != "DF":
                    continue
                subject = _first_cited_concept(line)
                if subject and subject != concept:
                    self._define(subject, block.name, line.text)

    def _define(self, name: str, block_name: str, token: str) -> None:
        self._concepts.setdefault(name, token)
        holders = self._defining.setdefault(name, [])
        if block_name not in holders:
            holders.append(block_name)

    def declared_edges(self) -> tuple[set[str], set[str]]:
        return set(), set()

    def mentions(self) -> set[str]:
        names: set[str] = set()
        for line in self._resolver.projection.lines:
            names |= extract_mentions(line.text)
        return names

    def resolve(self, names: set[str]) -> dict[str, str]:
        return {
            name: self._concepts.get(name, "unresolved:no concept block")
            for name in names
        }

    def collisions(self, names: set[str]) -> dict[str, list[str]]:
        """Names defined by more than one block."""
        return {
            name: self._defining[name]
            for name in names
            if len(self._defining.get(name, ())) > 1
        }


def index_dangling_mentions(start: Path | str) -> list[NetworkFinding]:
    """Run the core dangling-mention check over the Index records."""
    provider = IndexSurfaceProvider.for_path(start)
    resolutions = provider.resolve(provider.mentions())
    return dangling_mention_findings(Path("index"), resolutions)


def index_block_collisions(start: Path | str) -> list[NetworkFinding]:
    """Advisory collision `Drift.POI`s for a concept defined by more than one block.

    A name defined twice is ambiguous. The linter reports it; the human resolves it
    (for instance by namespacing) — the tool never repairs.
    """
    provider = IndexSurfaceProvider.for_path(start)
    findings: list[NetworkFinding] = []
    for name, blocks in sorted(provider.collisions(provider.mentions()).items()):
        where = ", ".join(sorted(blocks))
        findings.append(
            network_finding(
                "block-collision",
                Path("index"),
                name,
                where,
                f"mention `{name}` is defined by {len(blocks)} blocks ({where})",
            )
        )
    return findings


__all__ = [
    "DEFINING_CHAPTERS",
    "IndexSurfaceProvider",
    "chapter_of",
    "concept_of",
    "index_block_collisions",
    "index_dangling_mentions",
]

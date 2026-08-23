"""Index backend on the shared linter core, reading records.

Proves the extensibility point: the Index plugs into the surface-agnostic
`tarav.skw.network` engine through `IndexSurfaceProvider`, and the edge-free
`dangling_mention_findings` fires exactly on a mention whose concept was removed.

Resolution is global within one `Index.Workspace`, so a name defined by two blocks
is a reported collision rather than a lookup order.
"""

from __future__ import annotations

from pathlib import Path

from tarav.indexlab import IndexResolver
from tarav.indexlab.model import (
    IndexRecord,
    Operation,
    RecordContext,
    SupportSet,
    TurnRef,
)
from tarav.skillware.index_surfaces import IndexSurfaceProvider, chapter_of, concept_of
from tarav.skw import SurfaceProvider, dangling_mention_findings

ADVISORY = "advisory"
_CONTEXT = RecordContext(session="s", horizon=TurnRef(address="t", hash="0" * 16))


class _Corpus:
    """Build a record stream the way a capture would, one block at a time."""

    def __init__(self) -> None:
        self._records: list[IndexRecord] = []

    def _add(self, operation: str, parameters: dict, assertions=()) -> None:
        ordinal = len(self._records) + 1
        self._records.append(
            IndexRecord(
                id=f"rec_{ordinal}",
                ordinal=ordinal,
                context=_CONTEXT,
                operation=Operation(type=operation, parameters=parameters),
                support=SupportSet(neighborhoods=()),
                assertions=assertions,
            )
        )

    def block(self, name: str, lines: tuple[tuple[str, str], ...] = ()) -> _Corpus:
        block_id = f"blk_{len(self._records)}"
        self._add(
            "block.create",
            {"block_id": block_id, "isoblock_id": f"iso{block_id}", "name": name},
        )
        for code, text in lines:
            line_id = f"lin_{len(self._records)}"
            self._add(
                "line.capture",
                {
                    "line_id": line_id,
                    "isoline_id": f"iso{line_id}",
                    "block_id": block_id,
                    "label": f"^{line_id}",
                    "text": text,
                },
                ({"line_type": code},),
            )
        return self

    def provider(self) -> IndexSurfaceProvider:
        return IndexSurfaceProvider(IndexResolver.from_records(tuple(self._records)))


def test_address_parts_split_depot_chapter_and_concept() -> None:
    assert concept_of("pkg/design#Alpha.Concept") == "Alpha.Concept"
    assert chapter_of("pkg/design#Alpha.Concept") == "design"
    # A block written on a product surface belongs to no chapter.
    assert chapter_of("@notes/live/1-note.md#Alpha.Concept") == ""


def test_the_provider_satisfies_the_surface_protocol() -> None:
    provider = _Corpus().block("pkg/design#Alpha.Concept").provider()
    assert isinstance(provider, SurfaceProvider)
    # The Index declares no block->block edges.
    assert provider.declared_edges() == (set(), set())


def test_a_mention_of_a_defined_concept_resolves() -> None:
    corpus = (
        _Corpus()
        .block("pkg/design#Alpha.Concept", (("DF", "`Alpha.Concept` is a thing"),))
        .block(
            "pkg/design#Beta.Concept", (("CT", "`Beta.Concept` cites `Alpha.Concept`"),)
        )
    )
    provider = corpus.provider()
    resolutions = provider.resolve(provider.mentions())
    assert not dangling_mention_findings(Path("index"), resolutions)


def test_a_mention_whose_concept_was_removed_dangles() -> None:
    provider = (
        _Corpus()
        .block(
            "pkg/design#Beta.Concept", (("CT", "`Beta.Concept` cites `Gone.Concept`"),)
        )
        .provider()
    )
    resolutions = provider.resolve(provider.mentions())
    findings = dangling_mention_findings(Path("index"), resolutions)
    assert [finding.key for finding in findings] == ["Gone.Concept"]


def test_an_inline_definition_defines_a_concept_without_a_block() -> None:
    provider = (
        _Corpus()
        .block(
            "pkg/design#Alpha.Concept",
            (
                ("DF", "`Alpha.Concept` is a thing"),
                ("DF", "`Inline.Thing` is defined inside another block's body"),
            ),
        )
        .block(
            "pkg/design#Beta.Concept", (("CT", "`Beta.Concept` cites `Inline.Thing`"),)
        )
        .provider()
    )
    resolutions = provider.resolve(provider.mentions())
    assert not dangling_mention_findings(Path("index"), resolutions)


# Only a defining chapter hosts Inline.Definitions; a note is not one.
def test_a_df_line_on_a_product_surface_is_not_an_inline_definition() -> None:
    provider = (
        _Corpus()
        .block(
            "@notes/live/1-note.md#Note.Block",
            (("DF", "`Note.Only.Thing` appears only here"),),
        )
        .block(
            "pkg/design#Beta.Concept",
            (("CT", "`Beta.Concept` cites `Note.Only.Thing`"),),
        )
        .provider()
    )
    resolutions = provider.resolve(provider.mentions())
    findings = dangling_mention_findings(Path("index"), resolutions)
    assert [finding.key for finding in findings] == ["Note.Only.Thing"]


def test_a_concept_defined_by_two_blocks_is_a_collision() -> None:
    provider = (
        _Corpus()
        .block("pkg/design#Alpha.Concept", (("DF", "`Alpha.Concept` here"),))
        .block(
            "other/design#Alpha.Concept",
            (("DF", "`Alpha.Concept` defined a second time"),),
        )
        .block(
            "pkg/design#Beta.Concept", (("CT", "`Beta.Concept` cites `Alpha.Concept`"),)
        )
        .provider()
    )
    collisions = provider.collisions(provider.mentions())
    assert sorted(collisions["Alpha.Concept"]) == [
        "other/design#Alpha.Concept",
        "pkg/design#Alpha.Concept",
    ]

"""The index `Skw.Backend`'s binding into the shared linter core.

Implements `SurfaceProvider` (`agentos.skwlint`) over an index depot so the
surface-agnostic drift engine can run over the index — the extensibility point
of Impl.Req 700: a new surface is a new provider, no new engine.

The index declares no block->block edges (blocks reference each other only via
Dotted.Name mentions), so `declared_edges` is empty and the meaningful check is
`dangling_mention_findings`: a mention that no longer resolves.

DORMANT — deliberately not wired into `agentos index linter`. A low-noise
production run needs an index-aware resolver that models canonical/plural
short-forms, `::`-scoped names, inline definitions, and cross-depot concepts;
this provider's resolver recognizes concept-block *headings* only, which is
complete for controlled fixtures but floods the real multi-depot index
(Impl.Req 700, Impl.Log — the deferred resolver design).
"""

from pathlib import Path

from agentos.index.model import parse_depot
from agentos.index.model.nodes import BlockHeading, KernelLine, Node
from agentos.skwlint import Poi, dangling_mention_findings, extract_mentions


def _line_act(node: Node) -> str | None:
    for span in node.spans:
        if span.kind == "type_bracket":
            return span.parsed.get("act")
    return None


def _first_cited_concept(node: Node) -> str | None:
    for span in node.spans:
        if span.kind == "concept_cite":
            return str(span.parsed.get("value"))
    return None


def _defined_concepts(depot_root: Path) -> dict[str, str]:
    """Every concept an index depot defines, mapped to a stable definition token.

    Two definition forms are recognized:

    - **block headings** — a concept with its own `##` block.
    - **`Inline.Definition`** (103) — a `[DF]` line that defines a concept
      inside another block's body, without a block of its own. Its subject is
      the first cited concept on the line; the block's own first `[DF]` names
      the heading (already indexed), so only *other* `[DF]` subjects are inline
      definitions.

    The token is the defining line's text, so a later change to the definition
    shifts it — the hook a future `dangling`/stale check keys on.
    """
    concepts: dict[str, str] = {}
    for document in parse_depot(depot_root).documents:
        for node in document.nodes:
            if isinstance(node, BlockHeading):
                name = str(node.parsed.get("path", "")).strip()
                if name:
                    concepts.setdefault(name, node.src)
            elif isinstance(node, KernelLine) and _line_act(node) == "DF":
                subject = _first_cited_concept(node)
                if subject:
                    concepts.setdefault(subject, node.src)
    return concepts


class IndexSurfaceProvider:
    """`SurfaceProvider` over an index depot.

    Resolves against every concept the depot *defines* — block headings and
    `Inline.Definition`s. The remaining real-index gaps (canonical/plural
    short-forms, `::`-scoped names, cross-depot concepts) are the documented
    follow-up resolver work, not a defect in this binding.
    """

    def __init__(self, depot_root: Path) -> None:
        self._depot_root = Path(depot_root)
        self._concepts = _defined_concepts(self._depot_root)

    def declared_edges(self) -> tuple[set[str], set[str]]:
        # the index declares no block->block dependencies
        return set(), set()

    def mentions(self) -> set[str]:
        names: set[str] = set()
        for path in sorted(self._depot_root.rglob("*.md")):
            names |= extract_mentions(path.read_text(encoding="utf-8"))
        return names

    def resolve(self, names: set[str]) -> dict[str, str]:
        return {
            name: self._concepts.get(name, "unresolved:no concept block")
            for name in names
        }


def index_dangling_mentions(depot_root: Path) -> list[Poi]:
    """Run the core dangling-mention check over an index depot (dormant path)."""
    provider = IndexSurfaceProvider(depot_root)
    resolutions = provider.resolve(provider.mentions())
    return dangling_mention_findings(Path(Path(depot_root).name), resolutions)

"""The index `Skw.Backend`'s binding into the shared linter core.

Implements `SurfaceProvider` (`agentos.skwlint`) over an index depot so the
surface-agnostic drift engine can run over the index — the extensibility point
of Impl.Req 700: a new surface is a new provider, no new engine.

The index declares no block->block edges (blocks reference each other only via
Dotted.Name mentions), so `declared_edges` is empty and the meaningful check is
`dangling_mention_findings`: a mention that no longer resolves.

DORMANT — deliberately not wired into `agentos index linter`. The resolver now
models block headings, `Inline.Definition`s, declared aliases, and resolves
across every engaged depot (multi-depot). It still does *not* model
canonical/plural short-forms (`Stable.Surfaces`->`Stable.Surface`), `::`-scoped
names, illustrative example placeholders, or concepts defined on non-index
skill surfaces — so it still over-reports on the real index and stays dormant
pending those (design-laden) rules (Impl.Req 700, Impl.Log).
"""

from pathlib import Path

from agentos.index.model import parse_depot
from agentos.index.model.nodes import BlockHeading, KernelLine, MetaLine, Node
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
    """Every concept one index depot defines, mapped to a stable definition token.

    Three definition forms are recognized:

    - **block headings** — a concept with its own `##` block.
    - **`Inline.Definition`** (103) — a `[DF]` line that defines a concept
      inside another block's body, without a block of its own. Its subject is
      the first cited concept on the line; the block's own first `[DF]` names
      the heading (already indexed), so only *other* `[DF]` subjects are inline
      definitions.
    - **declared aliases** — a `### meta` `- aliases:` line naming alternate
      dotted names for the enclosing concept (e.g. `Touched.Variable` for
      `Hugentic.Variable`).

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
            elif isinstance(node, MetaLine) and node.src.strip().startswith("- aliases:"):
                for alias in extract_mentions(node.src):
                    concepts.setdefault(alias, node.src)
    return concepts


def _engaged_concepts(depots: tuple[Path, ...]) -> dict[str, str]:
    """Union the defined concepts across every engaged depot (multi-depot)."""
    concepts: dict[str, str] = {}
    for depot in depots:
        for name, token in _defined_concepts(depot).items():
            concepts.setdefault(name, token)
    return concepts


class IndexSurfaceProvider:
    """`SurfaceProvider` over an index depot.

    Mentions come from `depot_root`; resolution runs against the concepts
    *defined* across `depot_root` plus any additional `engaged_depots` — block
    headings, `Inline.Definition`s, and declared aliases. The remaining
    real-index gaps (canonical/plural short-forms, `::`-scoped names, example
    placeholders, non-index skill-surface concepts) are the documented
    follow-up resolver work, not a defect in this binding.
    """

    def __init__(
        self, depot_root: Path, *, engaged_depots: tuple[Path, ...] = ()
    ) -> None:
        self._depot_root = Path(depot_root)
        depots = (self._depot_root, *(Path(d) for d in engaged_depots))
        self._concepts = _engaged_concepts(depots)

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


def index_dangling_mentions(
    depot_root: Path, engaged_depots: tuple[Path, ...] = ()
) -> list[Poi]:
    """Run the core dangling-mention check over an index depot (dormant path)."""
    provider = IndexSurfaceProvider(depot_root, engaged_depots=engaged_depots)
    resolutions = provider.resolve(provider.mentions())
    return dangling_mention_findings(Path(Path(depot_root).name), resolutions)

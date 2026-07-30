# $kw: ^index-skw-network --from POI.System --from POI.Linter --note [CT] Index drift consumes domain-owned Skw.Network findings before POI adaptation ^c20260729-49u
"""The index `Skw.Backend`'s binding into the shared linter core.

Implements `SurfaceProvider` (`agentos.skw.network`) over an index depot so the
surface-agnostic drift engine can run over the index — the extensibility point
of Impl.Req 700: a new surface is a new provider, no new engine.

The index declares no block->block edges (blocks reference each other only via
Dotted.Name mentions), so `declared_edges` is empty and the meaningful check is
`dangling_mention_findings`: a mention that no longer resolves.

Wired into `agentos index linter` as a **default-off** check (`dangling-mention`,
Impl.Req 702): opt in with `--check dangling-mention`. It is off by default
because the resolver still over-reports on the real index — it models block
headings, `Inline.Definition`s, declared aliases, and resolves across declared
`Index.Depot.Dependency` depots, but not yet canonical/plural short-forms
(`Stable.Surfaces`->`Stable.Surface`), `::`-scoped names, illustrative example
placeholders, or concepts defined on non-index skill surfaces (design-laden
rules, Impl.Req 700/701 Impl.Log).
"""

from pathlib import Path

from agentos.index.depot_deps import resolve_dependency_depots
from agentos.index.model import parse_depot
from agentos.index.model.nodes import BlockHeading, KernelLine, MetaLine, Node
from agentos.skw import (
    NetworkFinding,
    dangling_mention_findings,
    extract_mentions,
    network_finding,
)


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
            elif isinstance(node, MetaLine) and node.src.strip().startswith(
                "- aliases:"
            ):
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


def _defining_depots(depots: tuple[Path, ...]) -> dict[str, list[Path]]:
    """Map each concept name to the visible depots that define it.

    A name defined in more than one visible depot is a collision — the
    `Index.Depot.Dependency` surfaces it (a `Drift.POI`), it does not resolve it.
    """
    defining: dict[str, list[Path]] = {}
    for depot in depots:
        for name in _defined_concepts(depot):
            defining.setdefault(name, []).append(depot)
    return defining


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
        self,
        depot_root: Path,
        *,
        engaged_depots: tuple[Path, ...] | None = None,
        home: Path | None = None,
    ) -> None:
        self._depot_root = Path(depot_root)
        if engaged_depots is None:
            # directed visibility: own + directly declared dependency depots
            deps, self.unresolved_dependencies = resolve_dependency_depots(
                self._depot_root, home
            )
        else:
            # explicit override (tests / callers supplying the visible set)
            deps, self.unresolved_dependencies = [Path(d) for d in engaged_depots], []
        depots = (self._depot_root, *deps)
        self._concepts = _engaged_concepts(depots)
        self._defining = _defining_depots(depots)

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

    def collisions(self, names: set[str]) -> dict[str, list[Path]]:
        """Names (from `names`) defined in more than one visible depot."""
        return {
            name: self._defining[name]
            for name in names
            if len(self._defining.get(name, ())) > 1
        }


def index_dangling_mentions(
    depot_root: Path, engaged_depots: tuple[Path, ...] | None = None
) -> list[NetworkFinding]:
    """Run the core dangling-mention check over an index depot.

    ``engaged_depots=None`` resolves the visible set through the depot's
    directed `Index.Depot.Dependency` declaration; an explicit tuple overrides it.
    """
    provider = IndexSurfaceProvider(depot_root, engaged_depots=engaged_depots)
    resolutions = provider.resolve(provider.mentions())
    return dangling_mention_findings(Path(Path(depot_root).name), resolutions)


def index_depot_collisions(
    depot_root: Path, engaged_depots: tuple[Path, ...] | None = None
) -> list[NetworkFinding]:
    """Advisory collision `Drift.POI`s for mentions defined in >1 visible depot.

    A mention whose name is defined in the depot and in one of its visible
    dependency depots is ambiguous. The linter reports it; the human resolves it
    (e.g. by namespacing) — the tool never repairs.
    """
    provider = IndexSurfaceProvider(depot_root, engaged_depots=engaged_depots)
    target_rel = Path(Path(depot_root).name)
    findings: list[NetworkFinding] = []
    for name, depots in sorted(provider.collisions(provider.mentions()).items()):
        where = ", ".join(sorted(d.name for d in depots))
        findings.append(
            network_finding(
                "depot-collision",
                target_rel,
                name,
                where,
                f"mention `{name}` is defined in {len(depots)} visible depots ({where})",
            )
        )
    return findings
